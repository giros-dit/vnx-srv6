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
        table_entry_exists, validate_table_id, main
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
                "rg": "fd00:0:1::5/64",
                "rc": "fd00:0:1::6/64"
            }
        }
        
        self.expected_loopbacks = {
            "ru": "fd00:0:1::1",
            "r1": "fd00:0:1::2", 
            "r2": "fd00:0:1::3",
            "r3": "fd00:0:1::4",
            "rg": "fd00:0:1::5",
            "rc": "fd00:0:1::6"
        }


class TestSSHExecution(TestSrcCore):
    """Tests para ejecución de comandos SSH"""
    
    # Test 1.1: Ejecución exitosa comando SSH
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
    
    # Test 1.2: Error en ejecución SSH
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
    
    # Test 2.1: Carga exitosa loopbacks
    @patch('builtins.open', new_callable=mock_open)
    def test_load_loopbacks_success(self, mock_file):
        """Test: Carga exitosa de loopbacks"""
        mock_file.return_value.read.return_value = json.dumps(self.network_data)
        
        result = load_loopbacks('/fake/path.json')
        
        self.assertEqual(result, self.expected_loopbacks)
        mock_file.assert_called_once_with('/fake/path.json')
    
    # Test 2.2: Path por defecto
    @patch('builtins.open', new_callable=mock_open)
    def test_load_loopbacks_default_path(self, mock_file):
        """Test: Uso del path por defecto"""
        mock_file.return_value.read.return_value = json.dumps(self.network_data)
        
        result = load_loopbacks()
        
        mock_file.assert_called_once_with('/app/networkinfo.json')
    
    # Test 2.3: Loopbacks vacíos
    @patch('builtins.open', new_callable=mock_open)
    def test_load_loopbacks_empty_loopbacks(self, mock_file):
        """Test: Manejo de loopbacks vacíos"""
        empty_data = {"loopbacks": {}}
        mock_file.return_value.read.return_value = json.dumps(empty_data)
        
        result = load_loopbacks()
        
        self.assertEqual(result, {})
    
    # Test 2.4: JSON sin clave loopbacks
    @patch('builtins.open', new_callable=mock_open)
    def test_load_loopbacks_no_loopbacks_key(self, mock_file):
        """Test: Manejo de JSON sin clave loopbacks"""
        invalid_data = {"graph": {"nodes": []}}
        mock_file.return_value.read.return_value = json.dumps(invalid_data)
        
        result = load_loopbacks()
        
        self.assertEqual(result, {})


class TestRuleExistence(TestSrcCore):
    """Tests para verificación de existencia de reglas"""
    
    # Test 3.1: Regla existe
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
    
    # Test 3.2: Regla con tabla diferente
    @patch('src.ssh_ru')
    def test_rule_exists_false_wrong_table(self, mock_ssh):
        """Test: Regla existe pero con tabla diferente"""
        mock_ssh.return_value = MagicMock(
            returncode=0,
            stdout=b"32764:  from all to fd00:0:2::1/64 lookup tunnel456\n"
        )
        
        result = rule_exists("fd00:0:2::1", 123)
        
        self.assertFalse(result)
    
    # Test 3.3: Sin reglas
    @patch('src.ssh_ru')
    def test_rule_exists_false_no_output(self, mock_ssh):
        """Test: No existe ninguna regla"""
        mock_ssh.return_value = MagicMock(
            returncode=0,
            stdout=b""
        )
        
        result = rule_exists("fd00:0:2::1", 123)
        
        self.assertFalse(result)
    
    # Test 3.4: Error SSH
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
    
    # Test 4.1: Ruta existe
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
    
    # Test 4.2: Ruta no existe
    @patch('src.ssh_ru')
    def test_route_exists_false(self, mock_ssh):
        """Test: Ruta no existe"""
        mock_ssh.return_value = MagicMock(
            returncode=0,
            stdout=b"fd00:0:3::1/64 encap seg6 mode encap segs fd00:0:1::4 dev eth1\n"
        )
        
        result = route_exists("fd00:0:2::1", 123)
        
        self.assertFalse(result)
    
    # Test 4.3: Error SSH
    @patch('src.ssh_ru')
    def test_route_exists_ssh_error(self, mock_ssh):
        """Test: Error en comando SSH"""
        mock_ssh.return_value = MagicMock(returncode=1)
        
        result = route_exists("fd00:0:2::1", 123)
        
        self.assertFalse(result)


class TestTableEntryExistence(TestSrcCore):
    """Tests para verificación de entradas en rt_tables"""
    
    # Test 5.1: Entrada existe
    @patch('src.ssh_ru')
    def test_table_entry_exists_true(self, mock_ssh):
        """Test: Entrada existe en rt_tables"""
        mock_ssh.return_value = MagicMock(returncode=0)
        
        result = table_entry_exists(123)
        
        self.assertTrue(result)
        mock_ssh.assert_called_once_with("grep -qx '123 tunnel123' /etc/iproute2/rt_tables")
    
    # Test 5.2: Entrada no existe
    @patch('src.ssh_ru')
    def test_table_entry_exists_false(self, mock_ssh):
        """Test: Entrada no existe"""
        mock_ssh.return_value = MagicMock(returncode=1)
        
        result = table_entry_exists(123)
        
        self.assertFalse(result)


class TestValidateTableId(TestSrcCore):
    """Tests para validación de IDs de tabla"""
    
    # Test 6.1: IDs válidos
    def test_validate_table_id_valid(self):
        """Test: IDs válidos"""
        valid_ids = [1, 2, 100, 252, 256, 1000]
        
        for tid in valid_ids:
            try:
                validate_table_id(tid)
            except ValueError:
                self.fail(f"validate_table_id rechazó ID válido {tid}")
    
    # Test 6.2: IDs reservados
    def test_validate_table_id_reserved(self):
        """Test: IDs reservados"""
        reserved_ids = [0, 253, 254, 255]
        
        for tid in reserved_ids:
            with self.assertRaises(ValueError) as cm:
                validate_table_id(tid)
            self.assertIn("reservado", str(cm.exception))


class TestMainFunction(TestSrcCore):
    """Tests para la función principal"""
    
    # Test 7.1: Instalación nueva
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
                path_json='["ru", "r1", "r3", "rg"]',
                table_id=123,
                new_table=True,
                delete_old=None,
                high_occupancy=False
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
    
    # Test 7.2: Actualización existente
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
                path_json='["ru", "r2", "r3", "rg"]',
                table_id=123,
                new_table=False,
                delete_old=None,
                high_occupancy=False
            )
            main()
        
        # Verificar llamadas SSH
        ssh_calls = [call[0][0] for call in mock_ssh.call_args_list]
        
        # Solo debe haber llamada para reemplazar ruta (no regla ni rt_tables)
        self.assertTrue(any("ip -6 route replace fd00:0:2::1/64" in call for call in ssh_calls))
        # No debe agregar nueva regla ni entrada rt_tables
        self.assertFalse(any("ip -6 rule add" in call for call in ssh_calls))
        self.assertFalse(any("echo" in call and "rt_tables" in call for call in ssh_calls))
    
    # Test 7.3: Con eliminación de tabla antigua
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
                path_json='["ru", "r1", "r3", "rg"]',
                table_id=123,
                new_table=True,
                delete_old=456,
                high_occupancy=False
            )
            main()
        
        # Verificar llamadas SSH
        ssh_calls = [call[0][0] for call in mock_ssh.call_args_list]
        
        # Debe eliminar regla antigua y agregar nueva
        self.assertTrue(any("ip -6 rule del to fd00:0:2::1/64 lookup tunnel456" in call for call in ssh_calls))
        self.assertTrue(any("ip -6 rule add to fd00:0:2::1/64 lookup tunnel123" in call for call in ssh_calls))
    
    # Test 7.4: Construcción de segmentos
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
                    path_json='["ru", "r1", "r3", "rg"]',
                    table_id=123,
                    new_table=False,
                    delete_old=None,
                    high_occupancy=False
                )
                main()
            
            # Verificar construcción de segmentos
            ssh_calls = [call[0][0] for call in mock_ssh.call_args_list]
            route_call = next(call for call in ssh_calls if "ip -6 route add" in call)
            
            # Los segmentos deben ser de r1, r3, rg (excluyendo ru)
            expected_segs = "fd00:0:1::2,fd00:0:1::4,fd00:0:1::5"
            self.assertIn(f"segs {expected_segs}", route_call)
    
    # Test 7.5: Flag de alta ocupación
    @patch('src.table_entry_exists')
    @patch('src.route_exists') 
    @patch('src.rule_exists')
    @patch('src.load_loopbacks')
    @patch('src.ssh_ru')
    def test_main_with_high_occupancy_flag(self, mock_ssh, mock_load, 
                                           mock_rule_exists, mock_route_exists, 
                                           mock_table_exists):
        """Test: Instalación con flag de alta ocupación"""
        # Configurar mocks
        mock_load.return_value = self.expected_loopbacks
        mock_rule_exists.return_value = False
        mock_route_exists.return_value = False
        mock_table_exists.return_value = False
        mock_ssh.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")
        
        # Ejecutar main con high_occupancy=True
        with patch('argparse.ArgumentParser.parse_args') as mock_parse:
            mock_parse.return_value = argparse.Namespace(
                dest_prefix='fd00:0:2::1/64',
                path_json='["ru", "r1", "r3", "rg"]',
                table_id=123,
                new_table=True,
                delete_old=None,
                high_occupancy=True
            )
            
            # Capturar salida para verificar el aviso
            with patch('builtins.print') as mock_print:
                main()
                
                # Verificar que se imprimió el aviso
                aviso_impreso = False
                for call in mock_print.call_args_list:
                    if "AVISO" in str(call) and "alta ocupación" in str(call):
                        aviso_impreso = True
                        break
                self.assertTrue(aviso_impreso)
    
    # Test 7.6: ID de tabla reservado
    @patch('src.load_loopbacks')
    @patch('src.ssh_ru')
    def test_main_reserved_table_id(self, mock_ssh, mock_load):
        """Test: Rechazo de IDs de tabla reservados"""
        # Configurar mocks
        mock_load.return_value = self.expected_loopbacks
        
        # Ejecutar main con ID reservado
        with patch('argparse.ArgumentParser.parse_args') as mock_parse:
            mock_parse.return_value = argparse.Namespace(
                dest_prefix='fd00:0:2::1/64',
                path_json='["ru", "r1", "r3", "rg"]',
                table_id=255,  # ID reservado
                new_table=True,
                delete_old=None,
                high_occupancy=False
            )
            
            # Capturar salida para verificar el error
            with patch('builtins.print') as mock_print:
                result = main()
                self.assertEqual(result, 1)  # Debe retornar error
                
                # Verificar que se imprimió el error
                error_impreso = False
                for call in mock_print.call_args_list:
                    if "ERROR" in str(call) and "reservado" in str(call):
                        error_impreso = True
                        break
                self.assertTrue(error_impreso)
    
    # Test 7.7: Delete-old ID reservado
    @patch('src.load_loopbacks')
    @patch('src.ssh_ru')
    def test_main_reserved_delete_old_id(self, mock_ssh, mock_load):
        """Test: Rechazo de ID reservado en delete_old"""
        # Configurar mocks
        mock_load.return_value = self.expected_loopbacks
        
        # Ejecutar main con delete_old ID reservado
        with patch('argparse.ArgumentParser.parse_args') as mock_parse:
            mock_parse.return_value = argparse.Namespace(
                dest_prefix='fd00:0:2::1/64',
                path_json='["ru", "r1", "r3", "rg"]',
                table_id=123,
                new_table=True,
                delete_old=254,  # ID reservado
                high_occupancy=False
            )
            
            # Capturar salida para verificar el error
            with patch('builtins.print') as mock_print:
                result = main()
                self.assertEqual(result, 1)  # Debe retornar error
                
                # Verificar que se imprimió el error
                error_impreso = False
                for call in mock_print.call_args_list:
                    if "ERROR" in str(call) and "Tabla antigua" in str(call):
                        error_impreso = True
                        break
                self.assertTrue(error_impreso)


class TestArgumentParsing(TestSrcCore):
    """Tests para parsing de argumentos"""
    
    # Test 8.1: Argumentos requeridos
    def test_argument_parser_required_args(self):
        """Test: Argumentos requeridos"""
        parser = argparse.ArgumentParser()
        parser.add_argument("dest_prefix")
        parser.add_argument("path_json")
        parser.add_argument("--table-id", type=int, required=True)
        parser.add_argument("--new-table", action="store_true")
        parser.add_argument("--delete-old", type=int)
        parser.add_argument("--high-occupancy", action="store_true")
        
        # Test con argumentos válidos
        args = parser.parse_args([
            'fd00:0:2::1/64',
            '["ru", "r1", "rg"]',
            '--table-id', '123'
        ])
        
        self.assertEqual(args.dest_prefix, 'fd00:0:2::1/64')
        self.assertEqual(args.path_json, '["ru", "r1", "rg"]')
        self.assertEqual(args.table_id, 123)
        self.assertFalse(args.new_table)
        self.assertIsNone(args.delete_old)
        self.assertFalse(args.high_occupancy)
    
    # Test 8.2: Todos los argumentos
    def test_argument_parser_with_all_flags(self):
        """Test: Todos los argumentos opcionales"""
        parser = argparse.ArgumentParser()
        parser.add_argument("dest_prefix")
        parser.add_argument("path_json")
        parser.add_argument("--table-id", type=int, required=True)
        parser.add_argument("--new-table", action="store_true")
        parser.add_argument("--delete-old", type=int)
        parser.add_argument("--high-occupancy", action="store_true")
        
        args = parser.parse_args([
            'fd00:0:2::1/64',
            '["ru", "r1", "rg"]',
            '--table-id', '123',
            '--new-table',
            '--delete-old', '456',
            '--high-occupancy'
        ])
        
        self.assertEqual(args.table_id, 123)
        self.assertTrue(args.new_table)
        self.assertEqual(args.delete_old, 456)
        self.assertTrue(args.high_occupancy)


class TestEdgeCases(TestSrcCore):
    """Tests para casos extremos y manejo de errores"""
    
    # Test 9.1: Caracteres especiales SSH
    @patch('src.ssh_ru')
    def test_ssh_command_with_special_characters(self, mock_ssh):
        """Test: Manejo de caracteres especiales en comandos SSH"""
        mock_ssh.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")
        
        # Test con comillas en el destino
        result = rule_exists("fd00:0:2::1'; echo 'hacked", 123)
        
        # Verificar que shlex.quote manejó correctamente los caracteres especiales
        call_args = mock_ssh.call_args[0][0]
        # No debe contener el comando de inyección sin escapar
        self.assertNotIn("echo 'hacked", call_args)
    
    # Test 9.2: Múltiples reglas
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
    
    # Test 9.3: Archivo no encontrado
    @patch('builtins.open', side_effect=FileNotFoundError)
    def test_load_loopbacks_file_not_found(self, mock_open):
        """Test: Archivo networkinfo.json no encontrado"""
        with self.assertRaises(FileNotFoundError):
            load_loopbacks()
    
    # Test 9.4: JSON inválido
    @patch('builtins.open', new_callable=mock_open)
    def test_load_loopbacks_invalid_json(self, mock_file):
        """Test: JSON inválido en networkinfo.json"""
        mock_file.return_value.read.return_value = "invalid json {"
        
        with self.assertRaises(json.JSONDecodeError):
            load_loopbacks()
    
    # Test 9.5: Path vacío
    @patch('src.ssh_ru')
    def test_empty_path_handling(self, mock_ssh):
        """Test: Manejo de path vacío"""
        with patch('src.load_loopbacks') as mock_load:
            mock_load.return_value = self.expected_loopbacks
            
            with patch('argparse.ArgumentParser.parse_args') as mock_parse:
                mock_parse.return_value = argparse.Namespace(
                    dest_prefix='fd00:0:2::1/64',
                    path_json='[]',  # Path vacío
                    table_id=123,
                    new_table=True,
                    delete_old=None,
                    high_occupancy=False
                )
                
                # Debería manejar el caso sin crash
                try:
                    main()
                except IndexError:
                    self.fail("main() no manejó correctamente un path vacío")
    
    # Test 9.6: Path con un solo nodo
    @patch('src.ssh_ru')
    def test_single_node_path(self, mock_ssh):
        """Test: Path con un solo nodo"""
        with patch('src.load_loopbacks') as mock_load:
            mock_load.return_value = self.expected_loopbacks
            
            with patch('argparse.ArgumentParser.parse_args') as mock_parse:
                mock_parse.return_value = argparse.Namespace(
                    dest_prefix='fd00:0:2::1/64',
                    path_json='["ru"]',  # Solo un nodo
                    table_id=123,
                    new_table=True,
                    delete_old=None,
                    high_occupancy=False
                )
                
                # La construcción de segmentos debería manejar esto
                main()
                
                # Verificar que se construyó un comando válido
                ssh_calls = [call[0][0] for call in mock_ssh.call_args_list]
                route_calls = [call for call in ssh_calls if "route" in call]
                # Con un solo nodo, no hay segmentos intermedios
                self.assertTrue(any("segs" in call for call in route_calls))


class TestIntegration(TestSrcCore):
    """Tests de integración end-to-end"""
    
    # Test 10.1: Flujo completo nuevo
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
                path_json='["ru", "r1", "r2", "rg"]',
                table_id=100,
                new_table=True,
                delete_old=None,
                high_occupancy=False
            )
            main()
        
        # Verify: Debe realizar todas las operaciones
        self.assertEqual(mock_ssh.call_count, 3)  # rt_tables + route + rule
        
        # Verificar orden y contenido de llamadas
        calls = [call[0][0] for call in mock_ssh.call_args_list]
        self.assertTrue(any("rt_tables" in call for call in calls))
        self.assertTrue(any("route add" in call for call in calls))
        self.assertTrue(any("rule add" in call for call in calls))
    
    # Test 10.2: Flujo completo actualización
    @patch('src.load_loopbacks')
    @patch('src.ssh_ru')
    @patch('src.rule_exists')
    @patch('src.route_exists')
    @patch('src.table_entry_exists')
    def test_complete_workflow_update_flow(self, mock_table_exists, mock_route_exists,
                                          mock_rule_exists, mock_ssh, mock_load):
        """Test: Flujo completo para actualización de flujo existente"""
        # Setup
        mock_load.return_value = self.expected_loopbacks
        mock_table_exists.return_value = True
        mock_route_exists.return_value = False  # Cambiando de tabla, ruta no existe en nueva tabla
        mock_rule_exists.side_effect = [True, True]  # Regla vieja existe, regla nueva existe
        mock_ssh.return_value = MagicMock(returncode=0, stdout=b"ok", stderr=b"")
        
        # Execute
        with patch('argparse.ArgumentParser.parse_args') as mock_parse:
            mock_parse.return_value = argparse.Namespace(
                dest_prefix='fd00:0:2::1/64',
                path_json='["ru", "r2", "r3", "rg"]',
                table_id=100,
                new_table=False,
                delete_old=99,
                high_occupancy=False
            )
            main()
        
        # Verify
        calls = [call[0][0] for call in mock_ssh.call_args_list]
        
        # Debe eliminar regla vieja
        self.assertTrue(any("rule del" in call and "tunnel99" in call for call in calls))
        # Debe agregar ruta con 'add' porque estamos cambiando de tabla
        self.assertTrue(any("route add" in call for call in calls))
        # No debe agregar nueva entrada rt_tables
        self.assertFalse(any("echo" in call and "rt_tables" in call for call in calls))


class TestDebugOutput(TestSrcCore):
    """Tests para salida de debug"""
    
    # Test 11.1: Formato de salida
    @patch('src.load_loopbacks')
    @patch('src.ssh_ru')
    @patch('builtins.print')
    def test_debug_output_format(self, mock_print, mock_ssh, mock_load):
        """Test: Formato correcto de salida de debug"""
        # Setup
        mock_load.return_value = self.expected_loopbacks
        mock_ssh.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")
        
        # Execute
        with patch('argparse.ArgumentParser.parse_args') as mock_parse:
            mock_parse.return_value = argparse.Namespace(
                dest_prefix='fd00:0:2::1/64',
                path_json='["ru", "r1", "rg"]',
                table_id=123,
                new_table=True,
                delete_old=None,
                high_occupancy=False
            )
            main()
        
        # Verificar que se imprimieron mensajes de debug
        print_calls = [str(call) for call in mock_print.call_args_list]
        
        # Debe imprimir los argumentos
        self.assertTrue(any("[src] Args:" in str(call) for call in print_calls))
        # Debe imprimir los loopbacks cargados
        self.assertTrue(any("[src] Loopbacks:" in str(call) for call in print_calls))
        # Debe imprimir Done al final
        self.assertTrue(any("[src] Done:" in str(call) for call in print_calls))


if __name__ == '__main__':
    # Ejecutar tests con verbosidad
    unittest.TextTestRunner(verbosity=2).run(
        unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])
    )