#!/bin/bash
TOPO_NAME=srv6
NS=c9s-srv6

yq() {
  docker run --rm -i -v "${PWD}":/workdir mikefarah/yq "$@"
}

PATCH=$(kubectl get deployment $(kubectl -n $NS get deployments | grep h2 | awk '{print $1}') -n $NS -o yaml | yq '.spec.template.metadata.annotations."k8s.v1.cni.cncf.io/networks" = "[{\"name\": \"net2032\", \"namespace\": \"c9s-srv6\", \"interface\": \"net2032\"}]"' -); kubectl patch deployment $(kubectl -n $NS get deployments | grep h2 | awk '{print $1}') -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get deployment $(kubectl -n $NS get deployments | grep r1 | awk '{print $1}') -n $NS -o yaml | yq '.spec.template.metadata.annotations."k8s.v1.cni.cncf.io/networks" = "[{\"name\": \"net1012\", \"namespace\": \"c9s-srv6\", \"interface\": \"net1012\"},{\"name\": \"net1014\", \"namespace\": \"c9s-srv6\", \"interface\": \"net1014\"},{\"name\": \"net2011\", \"namespace\": \"c9s-srv6\", \"interface\": \"net2011\"}]"' -); kubectl patch deployment $(kubectl -n $NS get deployments | grep r1 | awk '{print $1}') -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get deployment $(kubectl -n $NS get deployments | grep r2 | awk '{print $1}') -n $NS -o yaml | yq '.spec.template.metadata.annotations."k8s.v1.cni.cncf.io/networks" = "[{\"name\": \"net1012\", \"namespace\": \"c9s-srv6\", \"interface\": \"net1012\"},{\"name\": \"net1023\", \"namespace\": \"c9s-srv6\", \"interface\": \"net1023\"}]"' -); kubectl patch deployment $(kubectl -n $NS get deployments | grep r2 | awk '{print $1}') -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get deployment $(kubectl -n $NS get deployments | grep r3 | awk '{print $1}') -n $NS -o yaml | yq '.spec.template.metadata.annotations."k8s.v1.cni.cncf.io/networks" = "[{\"name\": \"net1023\", \"namespace\": \"c9s-srv6\", \"interface\": \"net1023\"},{\"name\": \"net1034\", \"namespace\": \"c9s-srv6\", \"interface\": \"net1034\"},{\"name\": \"net2032\", \"namespace\": \"c9s-srv6\", \"interface\": \"net2032\"}]"' -); kubectl patch deployment $(kubectl -n $NS get deployments | grep r3 | awk '{print $1}') -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get deployment $(kubectl -n $NS get deployments | grep r4 | awk '{print $1}') -n $NS -o yaml | yq '.spec.template.metadata.annotations."k8s.v1.cni.cncf.io/networks" = "[{\"name\": \"net1014\", \"namespace\": \"c9s-srv6\", \"interface\": \"net1014\"},{\"name\": \"net1034\", \"namespace\": \"c9s-srv6\", \"interface\": \"net1034\"}]"' -); kubectl patch deployment $(kubectl -n $NS get deployments | grep r4 | awk '{print $1}') -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get deployment $(kubectl -n $NS get deployments | grep h1 | awk '{print $1}') -n $NS -o yaml | yq '.spec.template.metadata.annotations."k8s.v1.cni.cncf.io/networks" = "[{\"name\": \"net2011\", \"namespace\": \"c9s-srv6\", \"interface\": \"net2011\"}]"' -); kubectl patch deployment $(kubectl -n $NS get deployments | grep h1 | awk '{print $1}') -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm srv6 -n $NS -o yaml | yq '.data.r1 |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net1012", "r1:eth1"]}] | tojson)'); kubectl patch cm srv6 -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm srv6 -n $NS -o yaml | yq '.data.r2 |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net1012", "r2:eth1"]}] | tojson)'); kubectl patch cm srv6 -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm srv6 -n $NS -o yaml | yq '.data.r2 |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net1023", "r2:eth2"]}] | tojson)'); kubectl patch cm srv6 -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm srv6 -n $NS -o yaml | yq '.data.r3 |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net1023", "r3:eth1"]}] | tojson)'); kubectl patch cm srv6 -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm srv6 -n $NS -o yaml | yq '.data.r1 |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net1014", "r1:eth2"]}] | tojson)'); kubectl patch cm srv6 -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm srv6 -n $NS -o yaml | yq '.data.r4 |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net1014", "r4:eth1"]}] | tojson)'); kubectl patch cm srv6 -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm srv6 -n $NS -o yaml | yq '.data.r4 |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net1034", "r4:eth2"]}] | tojson)'); kubectl patch cm srv6 -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm srv6 -n $NS -o yaml | yq '.data.r3 |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net1034", "r3:eth2"]}] | tojson)'); kubectl patch cm srv6 -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm srv6 -n $NS -o yaml | yq '.data.h1 |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net2011", "h1:eth1"]}] | tojson)'); kubectl patch cm srv6 -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm srv6 -n $NS -o yaml | yq '.data.r1 |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net2011", "r1:eth3"]}] | tojson)'); kubectl patch cm srv6 -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm srv6 -n $NS -o yaml | yq '.data.h2 |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net2032", "h2:eth1"]}] | tojson)'); kubectl patch cm srv6 -n $NS -o yaml --patch "$PATCH"
PATCH=$(kubectl get cm srv6 -n $NS -o yaml | yq '.data.r3 |= (. | fromjson | .topology.links += [{"endpoints": ["macvlan:net2032", "r3:eth3"]}] | tojson)'); kubectl patch cm srv6 -n $NS -o yaml --patch "$PATCH"
kubectl rollout restart deployment $(kubectl -n $NS get deployments | grep r1 | awk '{print $1}') -n $NS
kubectl rollout restart deployment $(kubectl -n $NS get deployments | grep r2 | awk '{print $1}') -n $NS
kubectl rollout restart deployment $(kubectl -n $NS get deployments | grep r3 | awk '{print $1}') -n $NS
kubectl rollout restart deployment $(kubectl -n $NS get deployments | grep r4 | awk '{print $1}') -n $NS
kubectl rollout restart deployment $(kubectl -n $NS get deployments | grep h1 | awk '{print $1}') -n $NS
kubectl rollout restart deployment $(kubectl -n $NS get deployments | grep h2 | awk '{print $1}') -n $NS
