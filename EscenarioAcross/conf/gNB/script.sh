#!/bin/bash
ip -6 route add fd00:0:1::2/64 encap seg6 mode encap segs fcff:4::1,fcff:5::1,fcff:12::1,fcff:11::1 via fd00:0:4::2
