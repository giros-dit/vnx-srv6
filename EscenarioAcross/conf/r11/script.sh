#!/bin/bash
ip -6 route add fd00:0:1::/126 encap seg6 mode encap segs fcff:4::1,fcff:5::1,fcff:13::1 dev eth3.111
