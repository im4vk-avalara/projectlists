FROM alpine:3.19

RUN apk add --no-cache nasm make

WORKDIR /work
