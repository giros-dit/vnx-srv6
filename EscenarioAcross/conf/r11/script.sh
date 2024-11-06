#!/bin/bash
ip -6 route add fd00:0:1::2/126 encap seg6 mode encap segs fcff:4::1,fcff:7::1,fcff:13::1 dev eth4.111
