#!/bin/bash
ip -6 route add fd00:0:2::/126 encap seg6 mode encap segs fcff:5::1,fcff:4::1,fcff:11::1 dev eth3.111
