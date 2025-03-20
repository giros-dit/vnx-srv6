# Clabernets ACROSS
Claberntes scenarios for studying and analyzing SRv6 (Segment Routing over IPv6 dataplane).


### Before launching the scenarios
 
Install:
- Containerlab
- kubectl
- docker
- kind

---

### Launch scenario
Too launch it, run the next commands:


```
kind create cluster --name c9s --config - <<EOF
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
  - role: control-plane
  - role: worker
  - role: worker
containerdConfigPatches:
- |-
  [plugins."io.containerd.grpc.v1.cri".containerd]
    discard_unpacked_layers = false
EOF
```

```
alias helm='docker run --network host -ti --rm -v $(pwd):/apps -w /apps \
    -v ~/.kube:/root/.kube -v ~/.helm:/root/.helm \
    -v ~/.config/helm:/root/.config/helm \
    -v ~/.cache/helm:/root/.cache/helm \
    alpine/helm:3.12.3'
```
```
helm upgrade --install --create-namespace --namespace c9s clabernetes oci://ghcr.io/srl-labs/clabernetes/clabernetes
```

```
kubectl apply -f https://kube-vip.io/manifests/rbac.yaml
kubectl apply -f https://raw.githubusercontent.com/kube-vip/kube-vip-cloud-provider/main/manifest/kube-vip-cloud-controller.yaml
kubectl create configmap --namespace kube-system kubevip --from-literal range-global=172.18.1.10-172.18.1.250
```

```
alias clabverter='sudo docker run --user $(id -u) \
    -v $(pwd):/clabernetes/work --rm \
    ghcr.io/giros-dit/clabernetes/clabverter'
```

```
kube-vip manifest daemonset --services --inCluster --arp --interface eth0 | kubectl apply -f -
```


```
kubectl apply -f ./converted
```

### IPv6 and interfaces Tables

#### final sistem - edge router


| **Dispositivo** | **Interfaces** | **VLAN** | **Dirección IPv6**   | **Router Interface** | **Router Interface IP**  |
|-----------------|----------------|----------|----------------------|----------------------|--------------------------|
| **h1**          | eth1.111       | 111      | fd00:0:1::1/127      | r1 - eth3.111        | fd00:0:1::/127           |
|                 | eth1.112       | 112      | fd00:0:1::3/127      | r1 - eth3.112        | fd00:0:1::2/127          |
| **h2**          | eth1.121       | 121      | fd00:0:2::1/127      | r3 - eth3.121        | fd00:0:2::/127           |
|                 | eth1.122       | 122      | fd00:0:2::3/127      | r3 - eth3.122        | fd00:0:2::2/127          |

#### Links router-router

| **Router A**    | **Router B**    | **Router A IPv6**        | **Router B IPv6**          |
|-----------------|-----------------|--------------------------|----------------------------|
| **r1  - eth1**  | **r2  - eth1**  | `fcf0:0:1:2::1/64`       | `fcf0:0:1:2::2/64`         |
| **r1  - eth2**  | **r4  - eth1**  | `fcf0:0:1:4::1/64`       | `fcf0:0:1:4::2/64`         |
| **r2  - eth2**  | **r3  - eth1**  | `fcf0:0:2:3::1/64`       | `fcf0:0:2:3::2/64`         |
| **r3  - eth2**  | **r4  - eth2**  | `fcf0:0:3:4::1/64`       | `fcf0:0:3:4::2/64`         |


#### Routers ID

| **Router**      | **ID**               |
|-----------------|----------------------|
| **r1**          | `fcff:1::1/32`       |
| **r2**          | `fcff:2::1/32`       |
| **r3**          | `fcff:3::1/32`       |
| **r4**          | `fcff:4::1/32`       |


#### CORE Sistem - router


| **Dispositivo** | **Interfaces** | **VLAN** | **Dirección IPv6**   | **Router Interface** | **Router Interface IP**  |
|-----------------|----------------|----------|----------------------|----------------------|--------------------------|
| **gNB1**        | eth1.111       | 111      | fd00:0:2::1/127      | R11 - eth4.111       | fd00:0:2::/127           |
|                 | eth1.112       | 112      | fd00:0:2::3/127      | R11 - eth4.112       | fd00:0:2::2/127          |
|                 | eth1.113       | 113      | fd00:0:2::5/127      | R11 - eth4.113       | fd00:0:2::4/127          |
| **gNB2**        | eth1.121       | 121      | fd00:0:3::1/127      | R12 - eth4.121       | fd00:0:3::/127           |
|                 | eth1.122       | 122      | fd00:0:3::3/127      | R12 - eth4.122       | fd00:0:3::2/127          |
|                 | eth1.123       | 123      | fd00:0:3::5/127      | R12 - eth4.123       | fd00:0:3::4/127          |
| **UPF**         | eth1.111       | 111      | fd00:0:1::1/127      | R13 - eth4.111       | fd00:0:1::/127           |
|                 | eth1.112       | 112      | fd00:0:1::3/127      | R13 - eth4.112       | fd00:0:1::2/127          |
|                 | eth1.113       | 113      | fd00:0:1::5/127      | R13 - eth4.113       | fd00:0:1::4/127          |
|                 | eth1.121       | 121      | fd00:0:1::7/127      | R13 - eth4.121       | fd00:0:1::6/127          |
|                 | eth1.122       | 122      | fd00:0:1::9/127      | R13 - eth4.122       | fd00:0:1::8/127          |
|                 | eth1.123       | 123      | fd00:0:1::b/127      | R13 - eth4.123       | fd00:0:1::a/127          |


#### Links router-router

| **Router A**    | **Router B**    | **Router A IPv6**        | **Router B IPv6**          |
|-----------------|-----------------|--------------------------|----------------------------|
| **r1  - eth2**  | **r2  - eth2**  | `fcf0:0:1:2::1/64`       | `fcf0:0:1:2::2/64`         |
| **r1  - eth3**  | **r4  - eth2**  | `fcf0:0:1:4::1/64`       | `fcf0:0:1:4::2/64`         |
| **r1  - eth4**  | **r11 - eth2**  | `fcf0:0:1:11::1/64`      | `fcf0:0:1:11::2/64`        |
| **r2  - eth3**  | **r3  - eth2**  | `fcf0:0:2:3::1/64`       | `fcf0:0:2:3::2/64`         |
| **r2  - eth4**  | **r5  - eth2**  | `fcf0:0:2:5::1/64`       | `fcf0:0:2:5::2/64`         |
| **r2  - eth5**  | **r12 - eth2**  | `fcf0:0:2:12::1/64`      | `fcf0:0:2:12::2/64`        |
| **r3  - eth3**  | **r7  - eth2**  | `fcf0:0:3:7::1/64`       | `fcf0:0:3:7::2/64`         |
| **r3  - eth4**  | **r12 - eth3**  | `fcf0:0:3:12::1/64`      | `fcf0:0:3:12::2/64`        |
| **r3  - eth5**  | **r13 - eth2**  | `fcf0:0:3:13::1/64`      | `fcf0:0:3:13::2/64`        |
| **r4  - eth3**  | **r6  - eth2**  | `fcf0:0:4:6::1/64`       | `fcf0:0:4:6::2/64`         |
| **r4  - eth4**  | **r11 - eth3**  | `fcf0:0:4:11::1/64`      | `fcf0:0:4:11::2/64`        |
| **r5  - eth3**  | **r6  - eth3**  | `fcf0:0:5:6::1/64`       | `fcf0:0:5:6::2/64`         |
| **r6  - eth4**  | **r7  - eth3**  | `fcf0:0:6:7::1/64`       | `fcf0:0:6:7::2/64`         |
| **r7  - eth4**  | **r13 - eth3**  | `fcf0:0:7:13::1/64`      | `fcf0:0:7:13::2/64`        |

#### Routers ID

| **Router**      | **ID**               |
|-----------------|----------------------|
| **r1**          | `fcff:1::1/32`       |
| **r2**          | `fcff:2::1/32`       |
| **r3**          | `fcff:3::1/32`       |
| **r4**          | `fcff:4::1/32`       |
| **r5**          | `fcff:5::1/32`       |
| **r6**          | `fcff:6::1/32`       |
| **r7**          | `fcff:7::1/32`       |
| **r11**         | `fcff:11::1/32`      |
| **r12**         | `fcff:12::1/32`      |
| **r13**         | `fcff:13::1/32`      |

---


### Linux commands for create tunnels

to create the 2 tunnels use the script 

```
./creatunnels.sh
```
