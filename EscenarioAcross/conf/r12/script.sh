#!/bin/bash
ip -6 route add fd00:0:1::16/126 encap seg6 mode encap segs fcff:5::1,fcff:7::1,fcff:13::1 dev eth4.123
