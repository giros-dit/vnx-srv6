#!/usr/bin/env python3
import unittest
import json
import subprocess
import argparse
from unittest.mock import patch, MagicMock, mock_open, call
import sys
import os

# Importar el módulo a testear
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Mock para evitar imports problemáticos
with patch('subprocess.run'):
    from src import (
        ssh_ru, load_loopbacks, rule_exists, route_exists, 
        table_entry_exists, main
    )


class TestSrcCore(unittest.TestCase):
    """Test suite para las funciones principales de src.py"""
    
    def setUp(self):
        """Configuración inicial para cada test"""
        # Mock data para networkinfo.json
        self.network_data = {
            "loopbacks": {
                "ru": "fd00:0:1::1/64",
                "r1": "fd00:0:1::2/64", 
                "r2": "fd00:0:1::3/64",
                "r3": "fd00:0:1::4/64",
                "rg1": "fd00:0:1::5/64",
                "rg2": "fd00:0:1::6/64"
            }
        }
        
        self.expected_loopbacks = {
            "ru": "fd00:0:1::1",
            "r1": "fd00:0:1::2", 
            "r2": "fd00:0:1::3",
            "r3": "fd00:0:1::4",
            "rg1": "fd00:0:1::5",
            "rg2": "fd00:0:1::6"
        }


class TestSSHExecution(TestSrcCore):
    """Tests para ejecución de comandos SSH"""
    
    @patch('subprocess.run')
    def test_ssh_ru_success(self, mock_run):
        """Test: Ejecución exitosa de comando SSH"""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=b"output text",
            stderr=b""
        )
        
        result = ssh_ru("ip -6 rule list")
        
        # Verificar llamada a subprocess
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        self.assertEqual(call_args[:2], ['ssh', '-o'])
        self.assertIn('StrictHostKeyChecking=no', call_args)
        self.assertIn('root@ru.across-tc32.svc.cluster.local', call_args)
        self.assertIn('PATH=$PATH:/usr/sbin:/sbin ip -6 rule list', call_args)
        
        # Verificar resultado
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"output text")
    
    @patch('subprocess.run')
    def test_ssh_ru_error(self, mock_run):
        """Test: Error en ejecución SSH"""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout=b"",
            stderr=b"command not found"
        )
        
        result = ssh_ru("invalid_command")
        
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr, b"command not found")


class TestLoopbackLoading(TestSrcCore):
    """Tests para carga de loopbacks"""
    
    @patch('builtins.open', new_callable=mock_open)
    def test_load_loopbacks_success(self, mock_file):
        """Test: Carga exitosa de loopbacks"""
        mock_file.return_value.read.return_value = json.dumps(self.network_data)
        
        result = load_loopbacks('/fake/path.json')
        
        self.assertEqual(result, self.expected_loopbacks)
        mock_file.assert_called_once_with('/fake/path.json')
    
    @patch('builtins.open', new_callable=mock_open)
    def test_load_loopbacks_default_path(self, mock_file):
        """Test: Uso del path por defecto"""
        mock_file.return_value.read.return_value = json.dumps(self.network_data)
        
        result = load_loopbacks()
        
        mock_file.assert_called_once_with('/app/networkinfo.json')
    
    @patch('builtins.open', new_callable=mock_open)
    def test_load_loopbacks_empty_loopbacks(self, mock_file):
        """Test: Manejo de loopbacks vacíos"""
        empty_data = {"loopbacks": {}}
        mock_file.return_value.read.return_value = json.dumps(empty_data)
        
        result = load_loopbacks()
        
        self.assertEqual(result, {})
    
    @patch('builtins.open', new_callable=mock_open)
    def test_load_loopbacks_no_loopbacks_key(self, mock_file):
        """Test: Manejo de JSON sin clave loopbacks"""
        invalid_data = {"graph": {"nodes": []}}
        mock_file.return_value.read.return_value = json.dumps(invalid_data)
        
        result = load_loopbacks()
        
        self.assertEqual(result, {})


class TestRuleExistence(TestSrcCore):
    """Tests para verificación de existencia de reglas"""
    
    @patch('src.ssh_ru')
    def test_rule_exists_true(self, mock_ssh):
        """Test: Regla existe"""
        mock_ssh.return_value = MagicMock(
            returncode=0,
            stdout=b"32764:  from all to fd00:0:2::1/64 lookup tunnel123\n"
        )
        
        result = rule_exists("fd00:0:2::1", 123)
        
        self.assertTrue(result)
        mock_ssh.assert_called_once_with("/usr/sbin/ip -6 rule show to fd00:0:2::1/64")
    
    @patch('src.ssh_ru')
    def test_rule_exists_false_wrong_table(self, mock_ssh):
        """Test: Regla existe pero con tabla diferente"""
        mock_ssh.return_value = MagicMock(
            returncode=0,
            stdout=b"32764:  from all to fd00:0:2::1/64 lookup tunnel456\n"
        )
        
        result = rule_exists("fd00:0:2::1", 123)
        
        self.assertFalse(result)
    
    @patch('src.ssh_ru')
    def test_rule_exists_false_no_output(self, mock_ssh):
        """Test: No existe ninguna regla"""
        mock_ssh.return_value = MagicMock(
            returncode=0,
            stdout=b""
        )
        
        result = rule_exists("fd00:0:2::1", 123)
        
        self.assertFalse(result)
    
    @patch('src.ssh_ru')
    def test_rule_exists_ssh_error(self, mock_ssh):
        """Test: Error en comando SSH"""
        mock_ssh.return_value = MagicMock(
            returncode=1,
            stdout=b"",
            stderr=b"error"
        )
        
        result = rule_exists("fd00:0:2::1", 123)
        
        self.assertFalse(result)


class TestRouteExistence(TestSrcCore):
    """Tests para verificación de existencia de rutas"""
    
    @patch('src.ssh_ru')
    def test_route_exists_true(self, mock_ssh):
        """Test: Ruta existe en la tabla"""
        mock_ssh.return_value = MagicMock(
            returncode=0,
            stdout=b"fd00:0:2::1/64 encap seg6 mode encap segs fd00:0:1::2,fd00:0:1::3 dev eth1\n"
        )
        
        result = route_exists("fd00:0:2::1", 123)
        
        self.assertTrue(result)
        mock_ssh.assert_called_once_with("/usr/sbin/ip -6 route show table tunnel123")
    
    @patch('src.ssh_ru')
    def test_route_exists_false(self, mock_ssh):
        """Test: Ruta no existe"""
        mock_ssh.return_value = MagicMock(
            returncode=0,
            stdout=b"fd00:0:3::1/64 encap seg6 mode encap segs fd00:0:1::4 dev eth1\n"
        )
        
        result = route_exists("fd00:0:2::1", 123)
        
        self.assertFalse(result)
    
    @patch('src.ssh_ru')
    def test_route_exists_ssh_error(self, mock_ssh):
        """Test: Error en comando SSH"""
        mock_ssh.return_value = MagicMock(returncode=1)
        
        result = route_exists("fd00:0:2::1", 123)
        
        self.assertFalse(result)


class TestTableEntryExistence(TestSrcCore):
    """Tests para verificación de entradas en rt_tables"""
    
    @patch('src.ssh_ru')
    def test_table_entry_exists_true(self, mock_ssh):
        """Test: Entrada existe en rt_tables"""
        mock_ssh.return_value = MagicMock(returncode=0)
        
        result = table_entry_exists(123)
        
        self.assertTrue(result)
        mock_ssh.assert_called_once_with("grep -qx '123 tunnel123' /etc/iproute2/rt_tables")
    
    @patch('src.ssh_ru')
    def test_table_entry_exists_false(self, mock_ssh):
        """Test: Entrada no existe"""
        mock_ssh.return_value = MagicMock(returncode=1)
        
        result = table_entry_exists(123)
        
        self.assertFalse(result)


class TestMainFunction(TestSrcCore):
    """Tests para la función principal"""
    
    @patch('src.table_entry_exists')
    @patch('src.route_exists') 
    @patch('src.rule_exists')
    @patch('src.load_loopbacks')
    @patch('src.ssh_ru')
    @patch('sys.argv')
    def test_main_new_installation(self, mock_argv, mock_ssh, mock_load, 
                                   mock_rule_exists, mock_route_exists, 
                                   mock_table_exists):
        """Test: Instalación nueva (sin reglas/rutas existentes)"""
        # Configurar argumentos
        mock_argv.__getitem__.side_effect = [
            'src.py',
            'fd00:0:2::1/64',
            '123', 
            '["ru", "r1", "r3", "rg1"]'
        ]
        
        # Configurar mocks
        mock_load.return_value = self.expected_loopbacks
        mock_rule_exists.return_value = False
        mock_route_exists.return_value = False  # ruta no existe -> usar 'add'
        mock_table_exists.return_value = False  # entrada tabla no existe
        mock_ssh.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")
        
        # Ejecutar main
        with patch('argparse.ArgumentParser.parse_args') as mock_parse:
            mock_parse.return_value = argparse.Namespace(
                dest_prefix='fd00:0:2::1/64',
                new_table_id=123,
                path_json='["ru", "r1", "r3", "rg1"]',
                delete_old=None
            )
            main()
        
        # Verificar llamadas SSH
        ssh_calls = [call[0][0] for call in mock_ssh.call_args_list]
        
        # Debe haber llamadas para:
        # 1. Agregar entrada a rt_tables 
        # 2. Instalar ruta (usando 'add')
        # 3. Agregar regla
        self.assertTrue(any("echo '123 tunnel123' >> /etc/iproute2/rt_tables" in call for call in ssh_calls))
        self.assertTrue(any("ip -6 route add fd00:0:2::1/64" in call for call in ssh_calls))
        self.assertTrue(any("ip -6 rule add to fd00:0:2::1/64 lookup tunnel123" in call for call in ssh_calls))
    
    @patch('src.table_entry_exists')
    @patch('src.route_exists') 
    @patch('src.rule_exists')
    @patch('src.load_loopbacks')
    @patch('src.ssh_ru')
    def test_main_update_existing(self, mock_ssh, mock_load, 
                                  mock_rule_exists, mock_route_exists, 
                                  mock_table_exists):
        """Test: Actualización de ruta existente"""
        # Configurar mocks
        mock_load.return_value = self.expected_loopbacks
        mock_rule_exists.return_value = True   # regla ya existe
        mock_route_exists.return_value = True  # ruta ya existe -> usar 'replace'
        mock_table_exists.return_value = True  # entrada tabla ya existe
        mock_ssh.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")
        
        # Ejecutar main
        with patch('argparse.ArgumentParser.parse_args') as mock_parse:
            mock_parse.return_value = argparse.Namespace(
                dest_prefix='fd00:0:2::1/64',
                new_table_id=123,
                path_json='["ru", "r2", "r3", "rg1"]',
                delete_old=None
            )
            main()
        
        # Verificar llamadas SSH
        ssh_calls = [call[0][0] for call in mock_ssh.call_args_list]
        
        # Solo debe haber llamada para reemplazar ruta (no regla ni rt_tables)
        self.assertTrue(any("ip -6 route replace fd00:0:2::1/64" in call for call in ssh_calls))
        # No debe agregar nueva regla ni entrada rt_tables
        self.assertFalse(any("ip -6 rule add" in call for call in ssh_calls))
        self.assertFalse(any("echo" in call and "rt_tables" in call for call in ssh_calls))
    
    @patch('src.table_entry_exists')
    @patch('src.route_exists') 
    @patch('src.rule_exists')
    @patch('src.load_loopbacks')
    @patch('src.ssh_ru')
    def test_main_with_delete_old(self, mock_ssh, mock_load, 
                                  mock_rule_exists, mock_route_exists, 
                                  mock_table_exists):
        """Test: Instalación con eliminación de regla antigua"""
        # Configurar mocks
        mock_load.return_value = self.expected_loopbacks
        # Primera llamada para regla antigua: existe
        # Segunda llamada para regla nueva: no existe
        mock_rule_exists.side_effect = [True, False]
        mock_route_exists.return_value = False
        mock_table_exists.return_value = False
        mock_ssh.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")
        
        # Ejecutar main
        with patch('argparse.ArgumentParser.parse_args') as mock_parse:
            mock_parse.return_value = argparse.Namespace(
                dest_prefix='fd00:0:2::1/64',
                new_table_id=123,
                path_json='["ru", "r1", "r3", "rg1"]',
                delete_old=456
            )
            main()
        
        # Verificar llamadas SSH
        ssh_calls = [call[0][0] for call in mock_ssh.call_args_list]
        
        # Debe eliminar regla antigua y agregar nueva
        self.assertTrue(any("ip -6 rule del to fd00:0:2::1/64 lookup tunnel456" in call for call in ssh_calls))
        self.assertTrue(any("ip -6 rule add to fd00:0:2::1/64 lookup tunnel123" in call for call in ssh_calls))
    
    @patch('src.load_loopbacks')
    def test_main_segs_construction(self, mock_load):
        """Test: Construcción correcta de segments"""
        mock_load.return_value = self.expected_loopbacks
        
        with patch('src.ssh_ru') as mock_ssh, \
             patch('src.rule_exists', return_value=False), \
             patch('src.route_exists', return_value=False), \
             patch('src.table_entry_exists', return_value=True):
            
            mock_ssh.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")
            
            # Ejecutar main
            with patch('argparse.ArgumentParser.parse_args') as mock_parse:
                mock_parse.return_value = argparse.Namespace(
                    dest_prefix='fd00:0:2::1/64',
                    new_table_id=123,
                    path_json='["ru", "r1", "r3", "rg1"]',
                    delete_old=None
                )
                main()
            
            # Verificar construcción de segmentos
            ssh_calls = [call[0][0] for call in mock_ssh.call_args_list]
            route_call = next(call for call in ssh_calls if "ip -6 route add" in call)
            
            # Los segmentos deben ser de r1, r3, rg1 (excluyendo ru)
            expected_segs = "fd00:0:1::2,fd00:0:1::4,fd00:0:1::5"
            self.assertIn(f"segs {expected_segs}", route_call)


class TestArgumentParsing(TestSrcCore):
    """Tests para parsing de argumentos"""
    
    def test_argument_parser_required_args(self):
        """Test: Argumentos requeridos"""
        parser = argparse.ArgumentParser()
        parser.add_argument("dest_prefix")
        parser.add_argument("new_table_id", type=int)
        parser.add_argument("path_json")
        parser.add_argument("--delete-old", type=int)
        
        # Test con argumentos válidos
        args = parser.parse_args([
            'fd00:0:2::1/64',
            '123',
            '["ru", "r1", "rg1"]'
        ])
        
        self.assertEqual(args.dest_prefix, 'fd00:0:2::1/64')
        self.assertEqual(args.new_table_id, 123)
        self.assertEqual(args.path_json, '["ru", "r1", "rg1"]')
        self.assertIsNone(args.delete_old)
    
    def test_argument_parser_with_delete_old(self):
        """Test: Argumento opcional delete-old"""
        parser = argparse.ArgumentParser()
        parser.add_argument("dest_prefix")
        parser.add_argument("new_table_id", type=int)
        parser.add_argument("path_json")
        parser.add_argument("--delete-old", type=int)
        
        args = parser.parse_args([
            'fd00:0:2::1/64',
            '123',
            '["ru", "r1", "rg1"]',
            '--delete-old', '456'
        ])
        
        self.assertEqual(args.delete_old, 456)


class TestEdgeCases(TestSrcCore):
    """Tests para casos extremos y manejo de errores"""
    
    @patch('src.ssh_ru')
    def test_ssh_command_with_special_characters(self, mock_ssh):
        """Test: Manejo de caracteres especiales en comandos SSH"""
        mock_ssh.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")
        
        # Test que los comandos se pasen correctamente a ssh_ru
        from src import ssh_ru
        result = ssh_ru("echo 'test with quotes'")
        
        # Verificar que se llamó ssh_ru con el comando esperado
        mock_ssh.assert_called_once_with("echo 'test with quotes'")
    
    @patch('src.ssh_ru')
    def test_rule_exists_multiple_matches(self, mock_ssh):
        """Test: Múltiples reglas, solo una coincide"""
        mock_ssh.return_value = MagicMock(
            returncode=0,
            stdout=b"32764:  from all to fd00:0:2::1/64 lookup tunnel123\n"
                   b"32765:  from all to fd00:0:2::1/64 lookup tunnel456\n"
        )
        
        result = rule_exists("fd00:0:2::1", 123)
        self.assertTrue(result)
        
        result = rule_exists("fd00:0:2::1", 789)
        self.assertFalse(result)
    
    @patch('builtins.open', side_effect=FileNotFoundError)
    def test_load_loopbacks_file_not_found(self, mock_open):
        """Test: Archivo networkinfo.json no encontrado"""
        with self.assertRaises(FileNotFoundError):
            load_loopbacks()
    
    @patch('builtins.open', new_callable=mock_open)
    def test_load_loopbacks_invalid_json(self, mock_file):
        """Test: JSON inválido en networkinfo.json"""
        mock_file.return_value.read.return_value = "invalid json {"
        
        with self.assertRaises(json.JSONDecodeError):
            load_loopbacks()


class TestIntegration(TestSrcCore):
    """Tests de integración end-to-end"""
    
    @patch('src.load_loopbacks')
    @patch('src.ssh_ru')
    @patch('src.rule_exists')
    @patch('src.route_exists')
    @patch('src.table_entry_exists')
    def test_complete_workflow_new_flow(self, mock_table_exists, mock_route_exists,
                                       mock_rule_exists, mock_ssh, mock_load):
        """Test: Flujo completo para nuevo flujo"""
        # Setup
        mock_load.return_value = self.expected_loopbacks
        mock_table_exists.return_value = False
        mock_route_exists.return_value = False
        mock_rule_exists.return_value = False
        mock_ssh.return_value = MagicMock(returncode=0, stdout=b"ok", stderr=b"")
        
        # Execute
        with patch('argparse.ArgumentParser.parse_args') as mock_parse:
            mock_parse.return_value = argparse.Namespace(
                dest_prefix='fd00:0:2::1/64',
                new_table_id=100,
                path_json='["ru", "r1", "r2", "rg1"]',
                delete_old=None
            )
            main()
        
        # Verify: Debe realizar todas las operaciones
        self.assertEqual(mock_ssh.call_count, 3)  # rt_tables + route + rule
        
        # Verificar orden y contenido de llamadas
        calls = [call[0][0] for call in mock_ssh.call_args_list]
        self.assertTrue(any("rt_tables" in call for call in calls))
        self.assertTrue(any("route add" in call for call in calls))
        self.assertTrue(any("rule add" in call for call in calls))


if __name__ == '__main__':
    # Ejecutar tests con verbosidad
    unittest.TextTestRunner(verbosity=2).run(
        unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])
    )
