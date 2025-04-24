import os
import json
import time
import signal
import subprocess
import pytest
from kafka import KafkaProducer
from minio import Minio
from testcontainers.minio import MinioContainer
from testcontainers.kafka import KafkaContainer

SCRIPT = "python3 ../mynetworkxkafkaminio.py"

@pytest.fixture(scope="module")
def minio_server():
    m = MinioContainer("minio/minio:latest")
    m.start()
    host = m.get_container_host_ip()
    port = m.get_exposed_port(9000)
    yield {
        "endpoint": f"{host}:{port}",
        "access_key": m.access_key,
        "secret_key": m.secret_key,
        "bucket": "testbucket"
    }
    m.stop()

@pytest.fixture(scope="module")
def kafka_server():
    with KafkaContainer() as k:
        yield k.get_bootstrap_server()

def wait_for_flow_file(minio_client, bucket, prefix="flows/", timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        objs = list(minio_client.list_objects(bucket, prefix))
        if objs:
            return objs[0].object_name
        time.sleep(0.5)
    pytest.fail(f"No hay fichero bajo {prefix} en bucket {bucket}")

def test_blackbox_integration(minio_server, kafka_server, tmp_path):
    # 1) Preparo entorno para que el SCRIPT vea el MinIO
    os.environ.update({
        "S3_ENDPOINT":   f"http://{minio_server['endpoint']}",
        "S3_ACCESS_KEY": minio_server["access_key"],
        "S3_SECRET_KEY": minio_server["secret_key"],
        "S3_BUCKET":     minio_server["bucket"]
    })

    # 2) Creo el bucket con el SDK minio
    client = Minio(
        minio_server["endpoint"],
        access_key=minio_server["access_key"],
        secret_key=minio_server["secret_key"],
        secure=False
    )
    if not client.bucket_exists(minio_server["bucket"]):
        client.make_bucket(minio_server["bucket"])

    # 3) Escribo final_output.json en tmp_path (cwd para el subprocess)
    final = tmp_path / "final_output.json"
    final.write_text(json.dumps({
        "graph": {
            "nodes": ["ru","r1","r2","rg"],
            "edges": [
                {"source":"ru","target":"r1","cost":1},
                {"source":"r1","target":"r2","cost":1},
                {"source":"r2","target":"rg","cost":1}
            ]
        },
        "loopbacks": {},
        "extremos": {"origen":"ru","destinos":["rg"]}
    }))

    # 4) Arranco el script en segundo plano
    proc = subprocess.Popen(
        SCRIPT.split(),
        cwd=str(tmp_path),
        env=os.environ.copy(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    try:
        # 4.1) Espero a que el consumidor Kafka se conecte
        time.sleep(1)

        # 5) Envío la métrica a Kafka
        producer = KafkaProducer(
            bootstrap_servers=[kafka_server],
            value_serializer=lambda v: json.dumps(v).encode()
        )
        msg = {
            "output_ml_metrics":[
                {"name":"node_network_power_consumption_variation_rate_occupation","value":"5"}
            ],
            "input_ml_metrics":[
                {"name":"node_network_router_capacity_occupation","value":"50"}
            ]
        }
        producer.send("ML_r1", msg)
        producer.flush()

        # 6) Espero suficiente para que el loop interno (sleep(5)) corra y escriba flows/
        time.sleep(6)

        # 7) Busco y valido el fichero en S3
        key = wait_for_flow_file(client, minio_server["bucket"])
        data = json.loads(
            client.get_object(minio_server["bucket"], key).read().decode()
        )
        assert data["flows"][0]["route"] == ["ru","r1","r2","rg"]

    finally:
        # 8) Apago el proceso de tu script
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
