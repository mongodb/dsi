FROM alpine:latest
ADD . /dsi
WORKDIR dsi
RUN echo "http://dl-4.alpinelinux.org/alpine/edge/community" >> /etc/apk/repositories
RUN mkdir ~/.matplotlib
RUN echo "backend: TkAgg" >> ~/.matplotlib/matplotlibrc
RUN set -xe \
    && apk update \
    && apk add curl gcc g++ \
    && apk add python-dev \
    && apk add lapack-dev \
    && apk add freetype-dev \
    && apk add gfortran \
    && apk add libffi-dev \
    && apk add openssl-dev \
    && apk add make \
    && apk add py-pip
RUN ln -s /usr/include/locale.h /usr/include/xlocale.h
RUN pip install --upgrade pip
RUN pip install -r requirements-dev.txt && python aws_tools/setup.py -q --no-user-cfg develop
