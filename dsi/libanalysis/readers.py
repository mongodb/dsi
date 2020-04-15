# pylint: skip-file
"""
NOTE: This is a local copy of the readers module, taken from the
support-tools/timeseries repository.

Provides functions to read FTDC data from either an FTDC file or from
a file containing serverStatus JSON documents, one per line. Each
reader takes a filename argument and returns a generator that yields a
sequence of chunks. Each chunk is a map from tuples keys to lists, where
the tuple key represents a path through a JSON document from root to leaf,
and the list is a list of values for that path.
"""


import collections
import json
import mmap
import os
import struct
import sys
import zlib

from six.moves import range


def _msg(*s):
    sys.stderr.write(" ".join(s))


#
# basic bson parser, to be extended as needed
# has optional special handling for ftdc:
#     returns numeric types as int64
#     ignores non-metric fields
# returns result as tree of OrderedDict, preserving order
#

_int32 = struct.Struct("<i")
_uint32 = struct.Struct("<I")
_int64 = struct.Struct("<q")
_uint64 = struct.Struct("<Q")
_double = struct.Struct("<d")

BSON = collections.OrderedDict


class BsonReaderException(Exception):
    """
    General exception when parsin bson.
    """

    pass


def _read_bson_doc(buf, at, ftdc=False):
    doc = BSON()
    doc_len = _int32.unpack_from(buf, at)[0]
    doc.bson_len = doc_len
    doc_end = at + doc_len
    at += 4
    while at < doc_end:
        bson_type = buf[at]
        at += 1
        name_end = buf.find(b"\0", at)
        n = buf[at:name_end]
        at = name_end + 1
        if bson_type == 0:  # eoo
            return doc
        elif bson_type == 1:  # _double
            v = _double.unpack_from(buf, at)[0]
            if ftdc:
                v = int(v)
            l = 8
        elif bson_type == 2:  # string
            l = _uint32.unpack_from(buf, at)[0]
            at += 4
            v = buf[at : at + l - 1] if not ftdc else None
        elif bson_type == 3:  # subdoc
            v = _read_bson_doc(buf, at, ftdc)
            l = v.bson_len
        elif bson_type == 4:  # array
            v = _read_bson_doc(buf, at, ftdc)
            l = v.bson_len
            if not ftdc:
                v = list(v.values())  # return as array
        elif bson_type == 8:  # bool
            v = buf[at]
            l = 1
        elif bson_type == 5:  # bindata
            l = _uint32.unpack_from(buf, at)[0]
            at += 5  # length plus subtype
            v = buf[at : at + l] if not ftdc else None
        elif bson_type == 7:  # objectid
            v = None  # xxx always ignore for now
            l = 12
        elif bson_type == 9:  # datetime
            v = _uint64.unpack_from(buf, at)[0]
            v = int(v) if ftdc else v / 1000.0
            l = 8
        elif bson_type == 16:  # _int32
            v = _int32.unpack_from(buf, at)[0]
            if ftdc:
                v = int(v)
            l = 4
        elif bson_type == 17:  # timestamp
            v = BSON()
            v[b"t"] = int(_uint32.unpack_from(buf, at)[0])  # seconds
            v[b"i"] = int(_uint32.unpack_from(buf, at + 4)[0])  # increment
            l = 8
        elif bson_type == 18:  # _int64
            v = int(_int64.unpack_from(buf, at)[0])
            l = 8
        elif bson_type == 0xFF or bson_type == 0x7F:  # minkey, maxkey
            v = None  # xxx always ignore for now
            l = 0
        else:
            err_msg = "unknown type %d(%x) at %d(%x)"
            raise BsonReaderException(err_msg % (bson_type, bson_type, at, at))
        if v != None:
            doc[n] = v
        at += l
    assert not "eoo not found"  # should have seen an eoo and returned


def _decode_chunk(chunk_doc, first_only):

    # our result is a map from metric keys to list of values for each metric key
    # a metric key is a path through the sample document represented as a tuple
    metrics = collections.OrderedDict()

    # decompress chunk data field
    data = chunk_doc[b"data"]
    metrics.chunk_len = len(data)
    data = data[4:]  # skip uncompressed length, we don't need it
    data = zlib.decompress(data)

    # read reference doc from chunk data, ignoring non-metric fields
    ref_doc = _read_bson_doc(data, 0, ftdc=True)
    # print_bson_doc(ref_doc)

    # traverse the reference document and extract map from metrics keys to values
    def extract_keys(doc, n=()):
        for k, v in doc.items():
            nn = n + (k,)
            if type(v) == BSON:
                extract_keys(v, nn)
            else:
                metrics[nn] = [v]

    extract_keys(ref_doc)

    # get nmetrics, ndeltas
    nmetrics = _uint32.unpack_from(data, ref_doc.bson_len)[0]
    ndeltas = _uint32.unpack_from(data, ref_doc.bson_len + 4)[0]
    nsamples = ndeltas + 1
    at = ref_doc.bson_len + 8
    if nmetrics != len(metrics):
        # xxx remove when SERVER-20602 is fixed
        _msg("ignoring bad chunk: nmetrics=%d, len(metrics)=%d" % (nmetrics, len(metrics)))
        return None
    metrics.nsamples = nsamples

    # only want first value in every chunk?
    if first_only:
        return metrics

    # unpacks ftdc packed ints
    def unpack(data, at):
        res = 0
        shift = 0
        while True:
            b = data[at]
            res |= (b & 0x7F) << shift
            at += 1
            if not (b & 0x80):
                if res > 0x7FFFFFFFFFFFFFFF:  # negative 64-bit value
                    res = int(res - 0x10000000000000000)
                return res, at
            shift += 7

    # unpack, run-length, delta, transpose the metrics
    nzeroes = 0
    for metric_values in metrics.values():
        value = metric_values[-1]
        for _ in range(ndeltas):
            if nzeroes:
                delta = 0
                nzeroes -= 1
            else:
                delta, at = unpack(data, at)
                if delta == 0:
                    nzeroes, at = unpack(data, at)
            value += delta
            metric_values.append(value)
    assert at == len(data)

    # our result
    return metrics


def read_ftdc(fn, first_only=False):

    """
    Read an ftdc file. fn may be either a single metrics file, or a
    directory containing a sequence of metrics files.
    """

    # process dir
    if os.path.isdir(fn):
        for f in sorted(os.listdir(fn)):
            for chunk in read_ftdc(os.path.join(fn, f)):
                yield chunk

    # process file
    else:

        # open and map file
        f = open(fn)
        buf = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        at = 0

        # traverse the file reading type 1 chunks
        while at < len(buf):
            try:
                chunk_doc = _read_bson_doc(buf, at)
                at += chunk_doc.bson_len
                if chunk_doc[b"type"] == 1:
                    yield _decode_chunk(chunk_doc, first_only)
            except Exception as e:
                raise Exception("bad bson doc: " + str(e))

        # bson docs should exactly cover file
        assert at == len(buf)


#
# xxx does not correctly handle schema change from one line to the next
#


def _parse(j, result, key):
    for k, v in j.items():
        kk = key
        if k != b"floatApprox":
            kk += (k,)
        if type(v) == dict:
            _parse(v, result, kk)
        else:
            result[kk].append(v)


def read_ss(fn):
    """Read a sequence of serverStatus JSON documents, one per line"""
    result = collections.defaultdict(list)
    for i, line in enumerate(open(fn)):
        j = json.loads(line)
        _parse(j, result, (b"serverStatus",))
        if i > 0 and i % 100 == 0:
            yield result
            result.clear()
    yield result


#
#
#


def read(fn):

    """Try all readers until one succeeds"""

    for f, name in ((read_ss, b"ss"), (read_ftdc, b"ftdc")):
        generator = f(fn)
        try:
            chunk = next(generator)
            if len(chunk) > 0:
                for chunk in generator:
                    yield chunk
                break
        except Exception as e:
            sys.stderr.write("does not appear to be %s: %s" % (name, str(e)))


#
# sniff test
#


if __name__ == "__main__":
    for chunk in read(sys.argv[1]):
        values = list(chunk.values())
        assert all(len(values[0]) == len(v) for v in values)
        print(
            "chunk, %d keys, %d values, key 0: %s, key 0 value 0: %d"
            % (
                len(list(chunk.keys())),
                len(values[0]),
                list(chunk.keys())[0],
                chunk[list(chunk.keys())[0]][0],
            )
        )
