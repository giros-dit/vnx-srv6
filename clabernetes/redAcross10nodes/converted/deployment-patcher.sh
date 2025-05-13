#!/bin/bash
TOPO_NAME=across
NS=across-tc32

yq() {
  docker run --rm -i -v "${PWD}":/workdir mikefarah/yq "$@"
}

PATCH=$(kubectl get deployment rupf -n $NS -o yaml | yq '.spec.template.metadata.annotations."k8s.v1.cni.cncf.io/networks" = "[{\"name\": \"net2001\", \"namespace\": \"across-tc32\", \"interface\": \"net2001\"},{\"name\": \"net2004\", \"namespace\": \"across-tc32\", \"interface\": \"net2004\"}]"' -); kubectl patch deployment rupf -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get deployment hgnb1-h1 -n $NS -o yaml | yq '.spec.template.metadata.annotations."k8s.v1.cni.cncf.io/networks" = "[{\"name\": \"net2002\", \"namespace\": \"across-tc32\", \"interface\": \"net2002\"}]"' -); kubectl patch deployment hgnb1-h1 -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get deployment hgnb1-h2 -n $NS -o yaml | yq '.spec.template.metadata.annotations."k8s.v1.cni.cncf.io/networks" = "[{\"name\": \"net2002\", \"namespace\": \"across-tc32\", \"interface\": \"net2002\"}]"' -); kubectl patch deployment hgnb1-h2 -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get deployment r1 -n $NS -o yaml | yq '.spec.template.metadata.annotations."k8s.v1.cni.cncf.io/networks" = "[{\"name\": \"net1001\", \"namespace\": \"across-tc32\", \"interface\": \"net1001\"},{\"name\": \"net1009\", \"namespace\": \"across-tc32\", \"interface\": \"net1009\"},{\"name\": \"net1002\", \"namespace\": \"across-tc32\", \"interface\": \"net1002\"}]"' -); kubectl patch deployment r1 -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get deployment rg1 -n $NS -o yaml | yq '.spec.template.metadata.annotations."k8s.v1.cni.cncf.io/networks" = "[{\"name\": \"net2005\", \"namespace\": \"across-tc32\", \"interface\": \"net2005\"},{\"name\": \"net1001\", \"namespace\": \"across-tc32\", \"interface\": \"net1001\"},{\"name\": \"net1005\", \"namespace\": \"across-tc32\", \"interface\": \"net1005\"}]"' -); kubectl patch deployment rg1 -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get deployment hupf-h1 -n $NS -o yaml | yq '.spec.template.metadata.annotations."k8s.v1.cni.cncf.io/networks" = "[{\"name\": \"net2001\", \"namespace\": \"across-tc32\", \"interface\": \"net2001\"}]"' -); kubectl patch deployment hupf-h1 -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get deployment hgnb2-h1 -n $NS -o yaml | yq '.spec.template.metadata.annotations."k8s.v1.cni.cncf.io/networks" = "[{\"name\": \"net2003\", \"namespace\": \"across-tc32\", \"interface\": \"net2003\"}]"' -); kubectl patch deployment hgnb2-h1 -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get deployment r4 -n $NS -o yaml | yq '.spec.template.metadata.annotations."k8s.v1.cni.cncf.io/networks" = "[{\"name\": \"net1005\", \"namespace\": \"across-tc32\", \"interface\": \"net1005\"},{\"name\": \"net1009\", \"namespace\": \"across-tc32\", \"interface\": \"net1009\"},{\"name\": \"net1006\", \"namespace\": \"across-tc32\", \"interface\": \"net1006\"}]"' -); kubectl patch deployment r4 -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get deployment r7 -n $NS -o yaml | yq '.spec.template.metadata.annotations."k8s.v1.cni.cncf.io/networks" = "[{\"name\": \"net1008\", \"namespace\": \"across-tc32\", \"interface\": \"net1008\"},{\"name\": \"net1012\", \"namespace\": \"across-tc32\", \"interface\": \"net1012\"},{\"name\": \"net1007\", \"namespace\": \"across-tc32\", \"interface\": \"net1007\"}]"' -); kubectl patch deployment r7 -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get deployment rg2 -n $NS -o yaml | yq '.spec.template.metadata.annotations."k8s.v1.cni.cncf.io/networks" = "[{\"name\": \"net2006\", \"namespace\": \"across-tc32\", \"interface\": \"net2006\"},{\"name\": \"net1013\", \"namespace\": \"across-tc32\", \"interface\": \"net1013\"},{\"name\": \"net1014\", \"namespace\": \"across-tc32\", \"interface\": \"net1014\"}]"' -); kubectl patch deployment rg2 -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get deployment ru -n $NS -o yaml | yq '.spec.template.metadata.annotations."k8s.v1.cni.cncf.io/networks" = "[{\"name\": \"net2004\", \"namespace\": \"across-tc32\", \"interface\": \"net2004\"},{\"name\": \"net1004\", \"namespace\": \"across-tc32\", \"interface\": \"net1004\"},{\"name\": \"net1008\", \"namespace\": \"across-tc32\", \"interface\": \"net1008\"}]"' -); kubectl patch deployment ru -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get deployment rgnb2 -n $NS -o yaml | yq '.spec.template.metadata.annotations."k8s.v1.cni.cncf.io/networks" = "[{\"name\": \"net2003\", \"namespace\": \"across-tc32\", \"interface\": \"net2003\"},{\"name\": \"net2006\", \"namespace\": \"across-tc32\", \"interface\": \"net2006\"}]"' -); kubectl patch deployment rgnb2 -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get deployment hgnb2-h3 -n $NS -o yaml | yq '.spec.template.metadata.annotations."k8s.v1.cni.cncf.io/networks" = "[{\"name\": \"net2003\", \"namespace\": \"across-tc32\", \"interface\": \"net2003\"}]"' -); kubectl patch deployment hgnb2-h3 -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get deployment r2 -n $NS -o yaml | yq '.spec.template.metadata.annotations."k8s.v1.cni.cncf.io/networks" = "[{\"name\": \"net1002\", \"namespace\": \"across-tc32\", \"interface\": \"net1002\"},{\"name\": \"net1010\", \"namespace\": \"across-tc32\", \"interface\": \"net1010\"},{\"name\": \"net1003\", \"namespace\": \"across-tc32\", \"interface\": \"net1003\"},{\"name\": \"net1013\", \"namespace\": \"across-tc32\", \"interface\": \"net1013\"}]"' -); kubectl patch deployment r2 -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get deployment r3 -n $NS -o yaml | yq '.spec.template.metadata.annotations."k8s.v1.cni.cncf.io/networks" = "[{\"name\": \"net1004\", \"namespace\": \"across-tc32\", \"interface\": \"net1004\"},{\"name\": \"net1012\", \"namespace\": \"across-tc32\", \"interface\": \"net1012\"},{\"name\": \"net1003\", \"namespace\": \"across-tc32\", \"interface\": \"net1003\"},{\"name\": \"net1014\", \"namespace\": \"across-tc32\", \"interface\": \"net1014\"}]"' -); kubectl patch deployment r3 -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get deployment r5 -n $NS -o yaml | yq '.spec.template.metadata.annotations."k8s.v1.cni.cncf.io/networks" = "[{\"name\": \"net1010\", \"namespace\": \"across-tc32\", \"interface\": \"net1010\"},{\"name\": \"net1011\", \"namespace\": \"across-tc32\", \"interface\": \"net1011\"}]"' -); kubectl patch deployment r5 -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get deployment r6 -n $NS -o yaml | yq '.spec.template.metadata.annotations."k8s.v1.cni.cncf.io/networks" = "[{\"name\": \"net1006\", \"namespace\": \"across-tc32\", \"interface\": \"net1006\"},{\"name\": \"net1011\", \"namespace\": \"across-tc32\", \"interface\": \"net1011\"},{\"name\": \"net1007\", \"namespace\": \"across-tc32\", \"interface\": \"net1007\"}]"' -); kubectl patch deployment r6 -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get deployment rgnb1 -n $NS -o yaml | yq '.spec.template.metadata.annotations."k8s.v1.cni.cncf.io/networks" = "[{\"name\": \"net2002\", \"namespace\": \"across-tc32\", \"interface\": \"net2002\"},{\"name\": \"net2005\", \"namespace\": \"across-tc32\", \"interface\": \"net2005\"}]"' -); kubectl patch deployment rgnb1 -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get deployment hgnb1-h3 -n $NS -o yaml | yq '.spec.template.metadata.annotations."k8s.v1.cni.cncf.io/networks" = "[{\"name\": \"net2002\", \"namespace\": \"across-tc32\", \"interface\": \"net2002\"}]"' -); kubectl patch deployment hgnb1-h3 -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get deployment hgnb2-h2 -n $NS -o yaml | yq '.spec.template.metadata.annotations."k8s.v1.cni.cncf.io/networks" = "[{\"name\": \"net2003\", \"namespace\": \"across-tc32\", \"interface\": \"net2003\"}]"' -); kubectl patch deployment hgnb2-h2 -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm across -n $NS -o yaml | yq '.data.r1 |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net1001", "r1:eth1"]}] | tojson)'); kubectl patch cm across -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm across -n $NS -o yaml | yq '.data.r1 |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net1009", "r1:eth2"]}] | tojson)'); kubectl patch cm across -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm across -n $NS -o yaml | yq '.data.r1 |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net1002", "r1:eth3"]}] | tojson)'); kubectl patch cm across -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm across -n $NS -o yaml | yq '.data.r2 |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net1002", "r2:eth1"]}] | tojson)'); kubectl patch cm across -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm across -n $NS -o yaml | yq '.data.r2 |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net1010", "r2:eth2"]}] | tojson)'); kubectl patch cm across -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm across -n $NS -o yaml | yq '.data.r2 |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net1003", "r2:eth3"]}] | tojson)'); kubectl patch cm across -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm across -n $NS -o yaml | yq '.data.r2 |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net1013", "r2:eth4"]}] | tojson)'); kubectl patch cm across -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm across -n $NS -o yaml | yq '.data.r3 |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net1004", "r3:eth1"]}] | tojson)'); kubectl patch cm across -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm across -n $NS -o yaml | yq '.data.r3 |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net1012", "r3:eth2"]}] | tojson)'); kubectl patch cm across -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm across -n $NS -o yaml | yq '.data.r3 |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net1003", "r3:eth3"]}] | tojson)'); kubectl patch cm across -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm across -n $NS -o yaml | yq '.data.r3 |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net1014", "r3:eth4"]}] | tojson)'); kubectl patch cm across -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm across -n $NS -o yaml | yq '.data.r4 |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net1005", "r4:eth1"]}] | tojson)'); kubectl patch cm across -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm across -n $NS -o yaml | yq '.data.r4 |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net1009", "r4:eth2"]}] | tojson)'); kubectl patch cm across -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm across -n $NS -o yaml | yq '.data.r4 |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net1006", "r4:eth3"]}] | tojson)'); kubectl patch cm across -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm across -n $NS -o yaml | yq '.data.r5 |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net1010", "r5:eth1"]}] | tojson)'); kubectl patch cm across -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm across -n $NS -o yaml | yq '.data.r5 |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net1011", "r5:eth2"]}] | tojson)'); kubectl patch cm across -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm across -n $NS -o yaml | yq '.data.r6 |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net1006", "r6:eth1"]}] | tojson)'); kubectl patch cm across -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm across -n $NS -o yaml | yq '.data.r6 |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net1011", "r6:eth2"]}] | tojson)'); kubectl patch cm across -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm across -n $NS -o yaml | yq '.data.r6 |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net1007", "r6:eth3"]}] | tojson)'); kubectl patch cm across -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm across -n $NS -o yaml | yq '.data.r7 |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net1008", "r7:eth1"]}] | tojson)'); kubectl patch cm across -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm across -n $NS -o yaml | yq '.data.r7 |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net1012", "r7:eth2"]}] | tojson)'); kubectl patch cm across -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm across -n $NS -o yaml | yq '.data.r7 |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net1007", "r7:eth3"]}] | tojson)'); kubectl patch cm across -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm across -n $NS -o yaml | yq '.data.rg1 |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net2005", "rg1:eth1"]}] | tojson)'); kubectl patch cm across -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm across -n $NS -o yaml | yq '.data.rg1 |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net1001", "rg1:eth2"]}] | tojson)'); kubectl patch cm across -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm across -n $NS -o yaml | yq '.data.rg1 |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net1005", "rg1:eth3"]}] | tojson)'); kubectl patch cm across -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm across -n $NS -o yaml | yq '.data.rg2 |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net2006", "rg2:eth1"]}] | tojson)'); kubectl patch cm across -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm across -n $NS -o yaml | yq '.data.rg2 |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net1013", "rg2:eth2"]}] | tojson)'); kubectl patch cm across -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm across -n $NS -o yaml | yq '.data.rg2 |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net1014", "rg2:eth3"]}] | tojson)'); kubectl patch cm across -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm across -n $NS -o yaml | yq '.data.ru |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net2004", "ru:eth1"]}] | tojson)'); kubectl patch cm across -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm across -n $NS -o yaml | yq '.data.ru |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net1004", "ru:eth2"]}] | tojson)'); kubectl patch cm across -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm across -n $NS -o yaml | yq '.data.ru |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net1008", "ru:eth3"]}] | tojson)'); kubectl patch cm across -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm across -n $NS -o yaml | yq '.data.rupf |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net2001", "rupf:eth1"]}] | tojson)'); kubectl patch cm across -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm across -n $NS -o yaml | yq '.data.rupf |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net2004", "rupf:eth2"]}] | tojson)'); kubectl patch cm across -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm across -n $NS -o yaml | yq '.data.rgnb1 |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net2002", "rgnb1:eth1"]}] | tojson)'); kubectl patch cm across -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm across -n $NS -o yaml | yq '.data.rgnb1 |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net2005", "rgnb1:eth2"]}] | tojson)'); kubectl patch cm across -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm across -n $NS -o yaml | yq '.data.rgnb2 |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net2003", "rgnb2:eth1"]}] | tojson)'); kubectl patch cm across -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm across -n $NS -o yaml | yq '.data.rgnb2 |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net2006", "rgnb2:eth2"]}] | tojson)'); kubectl patch cm across -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm across -n $NS -o yaml | yq '.data.hupf-h1 |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net2001", "hupf-h1:eth1"]}] | tojson)'); kubectl patch cm across -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm across -n $NS -o yaml | yq '.data.hgnb1-h1 |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net2002", "hgnb1-h1:eth1"]}] | tojson)'); kubectl patch cm across -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm across -n $NS -o yaml | yq '.data.hgnb1-h2 |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net2002", "hgnb1-h2:eth1"]}] | tojson)'); kubectl patch cm across -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm across -n $NS -o yaml | yq '.data.hgnb1-h3 |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net2002", "hgnb1-h3:eth1"]}] | tojson)'); kubectl patch cm across -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm across -n $NS -o yaml | yq '.data.hgnb2-h1 |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net2003", "hgnb2-h1:eth1"]}] | tojson)'); kubectl patch cm across -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm across -n $NS -o yaml | yq '.data.hgnb2-h2 |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net2003", "hgnb2-h2:eth1"]}] | tojson)'); kubectl patch cm across -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm across -n $NS -o yaml | yq '.data.hgnb2-h3 |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net2003", "hgnb2-h3:eth1"]}] | tojson)'); kubectl patch cm across -n $NS -o yaml --patch "$PATCH"
kubectl rollout restart deployment r1 -n $NS
kubectl rollout restart deployment r2 -n $NS
kubectl rollout restart deployment r3 -n $NS
kubectl rollout restart deployment r4 -n $NS
kubectl rollout restart deployment r5 -n $NS
kubectl rollout restart deployment r6 -n $NS
kubectl rollout restart deployment r7 -n $NS
kubectl rollout restart deployment rg1 -n $NS
kubectl rollout restart deployment rg2 -n $NS
kubectl rollout restart deployment ru -n $NS
kubectl rollout restart deployment rupf -n $NS
kubectl rollout restart deployment rgnb1 -n $NS
kubectl rollout restart deployment rgnb2 -n $NS
kubectl rollout restart deployment hupf-h1 -n $NS
kubectl rollout restart deployment hgnb1-h1 -n $NS
kubectl rollout restart deployment hgnb1-h2 -n $NS
kubectl rollout restart deployment hgnb1-h3 -n $NS
kubectl rollout restart deployment hgnb2-h1 -n $NS
kubectl rollout restart deployment hgnb2-h2 -n $NS
kubectl rollout restart deployment hgnb2-h3 -n $NS
