kubectl create configmap final-output --from-file=final_output.json
kubectl apply -f controller.yml