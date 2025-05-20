# conftest.py
import pytest
import os
from unittest.mock import patch, MagicMock


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Configuración global para todo el entorno de testing"""
    
    # Mock de variables de entorno S3/MinIO
    with patch.dict('os.environ', {
        'S3_ENDPOINT': 'http://localhost:9000',
        'S3_ACCESS_KEY': 'test_key',
        'S3_SECRET_KEY': 'test_secret',
        'S3_BUCKET': 'test_bucket',
        'ENERGYAWARE': 'true',
        'DEBUG_COSTS': 'false'
    }):
        # Mock del cliente boto3/S3
        with patch('boto3.client') as mock_boto_client:
            mock_s3_client = MagicMock()
            
            # Configurar comportamientos del mock S3
            mock_s3_client.head_bucket.return_value = None
            mock_s3_client.list_objects_v2.return_value = {'Contents': []}
            mock_s3_client.put_object.return_value = None
            mock_s3_client.get_object.return_value = MagicMock()
            
            mock_boto_client.return_value = mock_s3_client
            
            # Mock de las funciones de inicialización S3
            with patch('pce.ensure_bucket_exists') as mock_ensure_bucket, \
                 patch('pce.ensure_flows_folder_exists') as mock_ensure_folder:
                
                # Configurar los mocks para no hacer nada
                mock_ensure_bucket.return_value = None
                mock_ensure_folder.return_value = None
                
                yield


@pytest.fixture(autouse=True)
def reset_globals():
    """Resetea el estado global antes de cada test"""
    # Importar después de configurar los mocks
    import pce
    
    # Limpiar estado global
    pce.router_state.clear()
    pce.metrics.update({
        "routes_recalculated": 0,
        "tables_created": 0,
        "nodes_removed": 0,
        "flows_updated": 0
    })
    
    yield
    
    # Limpiar después del test
    pce.router_state.clear()
