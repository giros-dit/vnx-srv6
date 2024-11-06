#!/bin/bash
ip -6 route add fd00:0:2::2/126 encap seg6 mode encap segs fcff:7::1,fcff:4::1,fcff:11::1 dev eth4.111
ip -6 route add fd00:0:3::a/126 encap seg6 mode encap segs fcff:7::1,fcff:5::1,fcff:12::1 dev eth4.123
