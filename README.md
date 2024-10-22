# vnx-srv6
VNX scenarios for studying and analyzing SRv6 (Segment Routing over IPv6 dataplane).


##  Across
To run the scenarios, it is necessary to add the following lines to the **/etc/sysctl.conf** file:

```
fs.file-max = 4194304
fs.inotify.max_queued_events = 2097152
fs.inotify.max_user_instances = 2097152
fs.inotify.max_user_watches = 2097152
```

Finally, restart the system or run **sysctl --system** to apply these changes.

#### Host - router

| Host        | Router     | Host IPv6               | Router IPv6              |
|-------------|------------|-------------------------|--------------------------|
| h1 - eth1   | gNB - eth3 | `fd00:0:1::2/64`        | `fd00:0:1::1/64`         |
| h2 - eth1   | gNB - eth4 | `fd00:0:2::2/64`        | `fd00:0:2::1/64`         |
| h3 - eth1   | gNB - eth5 | `fd00:0:3::2/64`        | `fd00:0:3::1/64`         |
| UPF - eth1  | r13 - eth4 | `fd00:0:4::2/64`        | `fd00:0:4::1/64`         |

#### Links router-router

| Router A    | Router B    | Router A IPv6            | Router B IPv6              |
|-------------|-------------|--------------------------|----------------------------|
| r1  - eth2  | r2  - eth2  | `fcf0:0:1:2::1/64`       | `fcf0:0:1:2::2/64`         |
| r1  - eth3  | r4  - eth2  | `fcf0:0:1:4::1/64`       | `fcf0:0:1:4::2/64`         |
| r1  - eth4  | r11 - eth2  | `fcf0:0:1:11::1/64`      | `fcf0:0:1:11::2/64`        |
| r2  - eth3  | r3  - eth2  | `fcf0:0:2:3::1/64`       | `fcf0:0:2:3::2/64`         |
| r2  - eth4  | r5  - eth2  | `fcf0:0:2:5::1/64`       | `fcf0:0:2:5::2/64`         |
| r2  - eth5  | r12 - eth2  | `fcf0:0:2:12::1/64`      | `fcf0:0:2:12::2/64`        |
| r3  - eth3  | r7  - eth2  | `fcf0:0:3:7::1/64`       | `fcf0:0:3:7::2/64`         |
| r3  - eth4  | r12 - eth3  | `fcf0:0:3:12::1/64`      | `fcf0:0:3:12::2/64`        |
| r3  - eth5  | r13 - eth2  | `fcf0:0:3:13::1/64`      | `fcf0:0:3:13::2/64`        |
| r4  - eth3  | r6  - eth2  | `fcf0:0:4:6::1/64`       | `fcf0:0:4:6::2/64`         |
| r4  - eth4  | r11 - eth3  | `fcf0:0:4:11::1/64`      | `fcf0:0:4:11::2/64`        |
| r5  - eth3  | r6  - eth3  | `fcf0:0:5:6::1/64`       | `fcf0:0:5:6::2/64`         |
| r6  - eth4  | r7  - eth3  | `fcf0:0:6:7::1/64`       | `fcf0:0:6:7::2/64`         |
| r7  - eth4  | r13 - eth3  | `fcf0:0:7:13::1/64`      | `fcf0:0:7:13::2/64`        |
| r11 - eth4  | gNB - eth2  | `fcf0:0:11:14::1/64`     | `fcf0:0:11:14::2/64`       |

#### Routers ID

| Router      | ID               |
|-------------|------------------|
| r1          | `fcff:1::1/32`   |
| r2          | `fcff:2::1/32`   |
| r3          | `fcff:3::1/32`   |
| r4          | `fcff:4::1/32`   |
| r5          | `fcff:5::1/32`   |
| r6          | `fcff:6::1/32`   |
| r7          | `fcff:7::1/32`   |
| r11         | `fcff:11::1/32`  |
| r12         | `fcff:12::1/32`  |
| r13         | `fcff:13::1/32`  |
| gNB         | `fcff:14::1/32`  |

## SRv6 tunnels

**gNB**
```
ip -6 route add fd00:0:4::/64 encap seg6 mode encap segs fcff:4::1,fcff:13::1 via fd00:0:1::2
```
**r13**
```
ip -6 route add fd00:0:1::/64 encap seg6 mode encap segs fcff:4::1,fcff:14::1 via fd00:0:4::2
```
