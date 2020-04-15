# SSL

We learned the hard way that SSL certificates really work best with hostnames. This directory now
contains real SSL certificates for `*.dsitest.dev`, signed by a real CA. (It doesn't matter which
one, but I used Comodo.) In `infrastructure_provisioning` we write /etc/hosts entries such that
hostnames like mongod0.dsitest.dev work inside the VPC, using the private `10.2.0.*` addresses.
This setup should make SSL with dsi hosts work as seamlessly as the Atlas experience is.

`dsitest.dev.pem` contains the signed cert and private key. The passphrase to the latter is
'server-perf'.

When uploading to MongoDB servers, the `.pem` file becomes `member.pem`. This is the filename that
was used in the previous configuration too.

For your convenience, here is the output of `openssl x509 -in -text`:

    $ openssl x509 -in dsitest.dev.pem -text

    Certificate:
        Data:
            Version: 3 (0x2)
            Serial Number:
                0f:cb:b5:c3:0f:4d:8e:aa:cf:4f:66:b9:23:b0:58:87
            Signature Algorithm: sha256WithRSAEncryption
            Issuer: C = GB, ST = Greater Manchester, L = Salford, O = Sectigo Limited, CN = Sectigo RSA Domain Validation Secure Server CA
            Validity
                Not Before: Jan  2 00:00:00 2020 GMT
                Not After : Jan  1 23:59:59 2021 GMT
            Subject: CN = *.dsitest.dev
            Subject Public Key Info:
                Public Key Algorithm: rsaEncryption
                    RSA Public-Key: (2048 bit)
                    Modulus:
                        00:a5:7b:7a:ed:9f:4f:e2:be:5e:47:9a:4f:73:fc:
                        78:21:98:ef:8a:40:d2:a4:73:fb:48:c4:37:16:a1:
                        3b:90:71:3d:45:cb:76:11:06:6e:7b:43:85:b8:21:
                        fd:43:d4:db:5f:e0:d8:a1:ec:7b:1f:83:0d:c4:1d:
                        90:37:f9:fa:cb:5c:62:11:f4:02:6e:b3:f1:21:7e:
                        94:38:26:fc:fb:a5:c8:12:2c:86:86:3d:23:ec:02:
                        eb:0a:be:e9:9c:c6:9e:e2:67:2f:2f:bf:55:e9:d5:
                        8a:38:5c:0c:44:00:ae:7e:22:ac:3e:82:bd:c9:c7:
                        10:ca:dd:bb:c0:ca:1f:9e:5f:2e:5c:79:be:e2:71:
                        5e:58:6d:89:a9:2b:7b:22:f7:91:1a:54:69:af:a9:
                        d5:d0:87:c1:e9:58:e8:89:a2:c7:86:42:51:46:8f:
                        d0:44:d1:f8:7d:5a:7e:8a:62:97:cc:0e:97:e5:0e:
                        d8:6b:b3:08:22:9c:90:14:75:e3:76:60:fb:66:a9:
                        df:18:dd:92:27:27:73:99:98:76:0e:8a:80:85:99:
                        fc:17:d0:65:2a:c8:6f:d9:0b:a2:0d:8c:71:a5:a0:
                        da:c9:6c:ff:cd:83:84:20:99:e3:ee:f7:f5:5d:58:
                        fd:ce:a5:cf:62:2b:4d:a5:a0:ba:b6:9e:bf:ba:86:
                        fb:19
                    Exponent: 65537 (0x10001)
            X509v3 extensions:
                X509v3 Authority Key Identifier: 
                    keyid:8D:8C:5E:C4:54:AD:8A:E1:77:E9:9B:F9:9B:05:E1:B8:01:8D:61:E1

                X509v3 Subject Key Identifier: 
                    0B:41:B9:CE:0C:48:8A:48:48:16:0A:B4:06:EE:2A:2E:65:3A:E1:AD
                X509v3 Key Usage: critical
                    Digital Signature, Key Encipherment
                X509v3 Basic Constraints: critical
                    CA:FALSE
                X509v3 Extended Key Usage: 
                    TLS Web Server Authentication, TLS Web Client Authentication
                X509v3 Certificate Policies: 
                    Policy: 1.3.6.1.4.1.6449.1.2.2.7
                    CPS: https://sectigo.com/CPS
                    Policy: 2.23.140.1.2.1

                Authority Information Access: 
                    CA Issuers - URI:http://crt.sectigo.com/SectigoRSADomainValidationSecureServerCA.crt
                    OCSP - URI:http://ocsp.sectigo.com

                X509v3 Subject Alternative Name: 
                    DNS:*.dsitest.dev, DNS:dsitest.dev
                CT Precertificate SCTs: 
                    Signed Certificate Timestamp:
                        Version   : v1 (0x0)
                        Log ID    : 7D:3E:F2:F8:8F:FF:88:55:68:24:C2:C0:CA:9E:52:89:
                                    79:2B:C5:0E:78:09:7F:2E:6A:97:68:99:7E:22:F0:D7
                        Timestamp : Jan  2 08:46:09.021 2020 GMT
                        Extensions: none
                        Signature : ecdsa-with-SHA256
                                    30:44:02:20:36:52:CC:82:2F:71:CB:15:34:9A:B1:03:
                                    1E:67:A7:4D:1B:84:89:6D:B8:E7:32:5F:1A:60:B4:DB:
                                    51:52:0E:66:02:20:37:D7:77:B3:69:52:5D:DF:47:32:
                                    6B:FF:FF:36:AA:9F:F5:DD:E4:48:62:62:49:93:AE:ED:
                                    D5:2B:65:52:32:1D
                    Signed Certificate Timestamp:
                        Version   : v1 (0x0)
                        Log ID    : 44:94:65:2E:B0:EE:CE:AF:C4:40:07:D8:A8:FE:28:C0:
                                    DA:E6:82:BE:D8:CB:31:B5:3F:D3:33:96:B5:B6:81:A8
                        Timestamp : Jan  2 08:46:09.002 2020 GMT
                        Extensions: none
                        Signature : ecdsa-with-SHA256
                                    30:45:02:20:2A:3B:DE:2B:89:D5:B9:8A:3A:1D:02:47:
                                    17:62:A6:4F:7D:A1:83:5F:C3:FD:97:91:1A:F8:E0:56:
                                    F2:96:B3:8A:02:21:00:E6:FB:59:32:06:F6:B5:F3:59:
                                    AA:88:B2:25:DA:D6:EF:70:49:1B:45:7E:D2:B2:2A:BA:
                                    AB:34:8D:23:8A:CF:DF
        Signature Algorithm: sha256WithRSAEncryption
            d4:38:24:56:1e:33:b4:61:88:02:2e:53:a9:b3:94:89:6a:e2:
            e7:c7:ef:0e:80:18:16:99:8f:98:f0:96:8f:4f:e1:1a:e4:ed:
            87:5e:64:43:db:56:3e:d7:c2:e8:73:2f:f2:31:d2:28:b4:4c:
            42:4c:1e:7d:d5:d2:01:10:4e:72:d2:13:86:21:a5:00:a9:73:
            c5:01:ab:36:c2:b9:c4:01:3d:d6:9e:9f:e4:ab:6c:46:88:ec:
            2e:e3:c9:59:9d:88:46:d3:81:33:32:49:60:d7:62:a3:76:0c:
            6d:d7:de:ef:35:54:ff:6d:d3:ab:a6:53:eb:6b:68:d2:52:b8:
            03:fa:89:42:09:d9:c8:6f:fe:21:77:e7:7f:2d:81:30:c6:4c:
            32:5c:6f:3b:3b:5b:94:dd:6f:dc:1f:fb:5a:b9:c2:2b:35:88:
            9c:20:db:c8:d0:e6:e7:34:40:88:cf:a2:74:47:29:04:60:6e:
            2e:8e:78:84:e5:9a:2f:36:da:e7:9d:ac:fd:90:5b:3e:73:e9:
            d3:af:61:c6:6d:53:9c:10:a1:d1:77:b6:9b:d7:e9:8e:81:fe:
            d5:6f:20:98:df:fb:ae:62:7d:5b:7a:df:87:e2:59:c8:50:c5:
            13:84:5c:00:fc:79:f8:00:60:1f:fc:3d:b6:52:73:31:37:db:
            d2:7a:b3:66
