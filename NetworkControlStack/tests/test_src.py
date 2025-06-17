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
        ssh_ru, load_loopbacks, route_exists_for_dest, main
    )


class TestSrcNoTables(unittest.TestCase):
    """Test suite para las funciones principales de src.py sin tablas"""
    
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


class TestSSHExecution(TestSrcNoTables):
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
        
        result = ssh_ru("ip -6 route list")
        
        # Verificar llamada a subprocess
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        self.assertEqual(call_args[:2], ['ssh', '-o'])
        self.assertIn('StrictHostKeyChecking=no', call_args)
        self.assertIn('root@ru.across-tc32.svc.cluster.local', call_args)
        self.assertIn('PATH=$PATH:/usr/sbin:/sbin ip -6 route list', call_args)
        
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


class TestLoopbackLoading(TestSrcNoTables):
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


class TestRouteExistence(TestSrcNoTables):
    """Tests para verificación de existencia de rutas"""
    
    # Test 3.1: Ruta existe
    @patch('src.ssh_ru')
    def test_route_exists_for_dest_true(self, mock_ssh):
        """Test: Ruta existe para el destino"""
        mock_ssh.return_value = MagicMock(
            returncode=0,
            stdout=b"fd00:0:2::1 encap seg6 mode encap segs fd00:0:1::2,fd00:0:1::3 dev eth1\n"
        )
        
        result = route_exists_for_dest("fd00:0:2::1")
        
        self.assertTrue(result)
        mock_ssh.assert_called_once_with("/usr/sbin/ip -6 route show to fd00:0:2::1")
    
    # Test 3.2: Ruta no existe
    @patch('src.ssh_ru')
    def test_route_exists_for_dest_false(self, mock_ssh):
        """Test: Ruta no existe"""
        mock_ssh.return_value = MagicMock(
            returncode=0,
            stdout=b""
        )
        
        result = route_exists_for_dest("fd00:0:2::1")
        
        self.assertFalse(result)
    
    # Test 3.3: Error SSH
    @patch('src.ssh_ru')
    def test_route_exists_for_dest_ssh_error(self, mock_ssh):
        """Test: Error en comando SSH"""
        mock_ssh.return_value = MagicMock(returncode=1)
        
        result = route_exists_for_dest("fd00:0:2::1")
        
        self.assertFalse(result)


class TestMainFunction(TestSrcNoTables):
    """Tests para la función principal"""
    
    # Test 4.1: Instalación nueva sin rutas existentes
    @patch('src.route_exists_for_dest')
    @patch('src.load_loopbacks')
    @patch('src.ssh_ru')
    def test_main_new_installation(self, mock_ssh, mock_load, mock_route_exists):
        """Test: Instalación nueva (sin rutas existentes)"""
        # Configurar mocks
        mock_load.return_value = self.expected_loopbacks
        mock_route_exists.return_value = False  # ruta no existe -> usar 'add'
        mock_ssh.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")
        
        # Ejecutar main
        with patch('argparse.ArgumentParser.parse_args') as mock_parse:
            mock_parse.return_value = argparse.Namespace(
                dest_prefix='fd00:0:2::1/64',
                path_json='["ru", "r1", "r3", "rg"]',
                replace=False,
                high_occupancy=False
            )
            main()
        
        # Verificar llamadas SSH
        ssh_calls = [call[0][0] for call in mock_ssh.call_args_list]
        
        # Debe instalar ruta usando 'add' (sin /64)
        self.assertTrue(any("ip -6 route add fd00:0:2::1" in call for call in ssh_calls))
        # Los segmentos deben ser de r1, r3, rg (excluyendo ru)
        expected_segs = "fd00:0:1::2,fd00:0:1::4,fd00:0:1::5"
        self.assertTrue(any(f"segs {expected_segs}" in call for call in ssh_calls))
    
    # Test 4.2: Actualización existente (usando replace)
    @patch('src.route_exists_for_dest')
    @patch('src.load_loopbacks')
    @patch('src.ssh_ru')
    def test_main_update_existing(self, mock_ssh, mock_load, mock_route_exists):
        """Test: Actualización de ruta existente"""
        # Configurar mocks
        mock_load.return_value = self.expected_loopbacks
        mock_route_exists.return_value = True  # ruta ya existe -> usar 'replace'
        mock_ssh.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")
        
        # Ejecutar main
        with patch('argparse.ArgumentParser.parse_args') as mock_parse:
            mock_parse.return_value = argparse.Namespace(
                dest_prefix='fd00:0:2::1/64',
                path_json='["ru", "r2", "r3", "rg"]',
                replace=False,
                high_occupancy=False
            )
            main()
        
        # Verificar llamadas SSH
        ssh_calls = [call[0][0] for call in mock_ssh.call_args_list]
        
        # Debe usar 'replace' porque la ruta ya existe (sin /64)
        self.assertTrue(any("ip -6 route replace fd00:0:2::1" in call for call in ssh_calls))
    
    # Test 4.3: Flag replace forzado
    @patch('src.route_exists_for_dest')
    @patch('src.load_loopbacks')
    @patch('src.ssh_ru')
    def test_main_with_replace_flag(self, mock_ssh, mock_load, mock_route_exists):
        """Test: Uso del flag --replace forzado"""
        # Configurar mocks
        mock_load.return_value = self.expected_loopbacks
        mock_route_exists.return_value = False  # ruta no existe
        mock_ssh.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")
        
        # Ejecutar main con flag --replace
        with patch('argparse.ArgumentParser.parse_args') as mock_parse:
            mock_parse.return_value = argparse.Namespace(
                dest_prefix='fd00:0:2::1/64',
                path_json='["ru", "r1", "r3", "rg"]',
                replace=True,  # Flag forzado
                high_occupancy=False
            )
            main()
        
        # Verificar llamadas SSH
        ssh_calls = [call[0][0] for call in mock_ssh.call_args_list]
        
        # Debe usar 'replace' porque el flag fue pasado (sin /64)
        self.assertTrue(any("ip -6 route replace fd00:0:2::1" in call for call in ssh_calls))
    
    # Test 4.4: Construcción de segmentos
    @patch('src.load_loopbacks')
    def test_main_segs_construction(self, mock_load):
        """Test: Construcción correcta de segments"""
        mock_load.return_value = self.expected_loopbacks
        
        with patch('src.ssh_ru') as mock_ssh, \
             patch('src.route_exists_for_dest', return_value=False):
            
            mock_ssh.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")
            
            # Ejecutar main
            with patch('argparse.ArgumentParser.parse_args') as mock_parse:
                mock_parse.return_value = argparse.Namespace(
                    dest_prefix='fd00:0:2::1/64',
                    path_json='["ru", "r1", "r3", "rg"]',
                    replace=False,
                    high_occupancy=False
                )
                main()
            
            # Verificar construcción de segmentos
            ssh_calls = [call[0][0] for call in mock_ssh.call_args_list]
            route_call = next(call for call in ssh_calls if "ip -6 route" in call)
            
            # Los segmentos deben ser de r1, r3, rg (excluyendo ru)
            expected_segs = "fd00:0:1::2,fd00:0:1::4,fd00:0:1::5"
            self.assertIn(f"segs {expected_segs}", route_call)
    
    # Test 4.5: Flag de alta ocupación
    @patch('src.route_exists_for_dest')
    @patch('src.load_loopbacks')
    @patch('src.ssh_ru')
    def test_main_with_high_occupancy_flag(self, mock_ssh, mock_load, mock_route_exists):
        """Test: Instalación con flag de alta ocupación"""
        # Configurar mocks
        mock_load.return_value = self.expected_loopbacks
        mock_route_exists.return_value = False
        mock_ssh.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")
        
        # Ejecutar main con high_occupancy=True
        with patch('argparse.ArgumentParser.parse_args') as mock_parse:
            mock_parse.return_value = argparse.Namespace(
                dest_prefix='fd00:0:2::1/64',
                path_json='["ru", "r1", "r3", "rg"]',
                replace=False,
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
    
    # Test 4.6: Comando completo con todas las opciones
    @patch('src.route_exists_for_dest')
    @patch('src.load_loopbacks')
    @patch('src.ssh_ru')
    def test_main_complete_command(self, mock_ssh, mock_load, mock_route_exists):
        """Test: Comando completo con todos los parámetros"""
        # Configurar mocks
        mock_load.return_value = self.expected_loopbacks
        mock_route_exists.return_value = False
        mock_ssh.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")
        
        # Ejecutar main
        with patch('argparse.ArgumentParser.parse_args') as mock_parse:
            mock_parse.return_value = argparse.Namespace(
                dest_prefix='fd00:0:2::1/64',
                path_json='["ru", "r1", "r2", "r3", "rg"]',
                replace=False,
                high_occupancy=False
            )
            main()
        
        # Verificar comando construido
        ssh_calls = [call[0][0] for call in mock_ssh.call_args_list]
        route_call = ssh_calls[0]
        
        # Verificar estructura del comando (sin /64)
        self.assertIn("ip -6 route add", route_call)
        self.assertIn("fd00:0:2::1", route_call)
        self.assertIn("encap seg6 mode encap", route_call)
        self.assertIn("dev eth1", route_call)
        
        # Verificar segmentos (excluye ru)
        expected_segs = "fd00:0:1::2,fd00:0:1::3,fd00:0:1::4,fd00:0:1::5"
        self.assertIn(f"segs {expected_segs}", route_call)


class TestArgumentParsing(TestSrcNoTables):
    """Tests para parsing de argumentos"""
    
    # Test 5.1: Argumentos requeridos
    def test_argument_parser_required_args(self):
        """Test: Argumentos requeridos"""
        parser = argparse.ArgumentParser()
        parser.add_argument("dest_prefix")
        parser.add_argument("path_json")
        parser.add_argument("--replace", action="store_true")
        parser.add_argument("--high-occupancy", action="store_true")
        
        # Test con argumentos válidos
        args = parser.parse_args([
            'fd00:0:2::1/64',
            '["ru", "r1", "rg"]'
        ])
        
        self.assertEqual(args.dest_prefix, 'fd00:0:2::1/64')
        self.assertEqual(args.path_json, '["ru", "r1", "rg"]')
        self.assertFalse(args.replace)
        self.assertFalse(args.high_occupancy)
    
    # Test 5.2: Todos los argumentos
    def test_argument_parser_with_all_flags(self):
        """Test: Todos los argumentos opcionales"""
        parser = argparse.ArgumentParser()
        parser.add_argument("dest_prefix")
        parser.add_argument("path_json")
        parser.add_argument("--replace", action="store_true")
        parser.add_argument("--high-occupancy", action="store_true")
        
        args = parser.parse_args([
            'fd00:0:2::1/64',
            '["ru", "r1", "rg"]',
            '--replace',
            '--high-occupancy'
        ])
        
        self.assertTrue(args.replace)
        self.assertTrue(args.high_occupancy)


class TestEdgeCases(TestSrcNoTables):
    """Tests para casos extremos y manejo de errores"""
    
    # Test 6.1: Caracteres especiales SSH
    @patch('src.ssh_ru')
    def test_ssh_command_with_special_characters(self, mock_ssh):
        """Test: Manejo de caracteres especiales en comandos SSH"""
        mock_ssh.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")
        
        # Test con comillas en el destino
        result = route_exists_for_dest("fd00:0:2::1'; echo 'hacked")
        
        # Verificar que shlex.quote manejó correctamente los caracteres especiales
        call_args = mock_ssh.call_args[0][0]
        # No debe contener el comando de inyección sin escapar
        self.assertNotIn("echo 'hacked", call_args)
    
    # Test 6.2: Archivo no encontrado
    @patch('builtins.open', side_effect=FileNotFoundError)
    def test_load_loopbacks_file_not_found(self, mock_open):
        """Test: Archivo networkinfo.json no encontrado"""
        with self.assertRaises(FileNotFoundError):
            load_loopbacks()
    
    # Test 6.3: JSON inválido
    @patch('builtins.open', new_callable=mock_open)
    def test_load_loopbacks_invalid_json(self, mock_file):
        """Test: JSON inválido en networkinfo.json"""
        mock_file.return_value.read.return_value = "invalid json {"
        
        with self.assertRaises(json.JSONDecodeError):
            load_loopbacks()
    
    # Test 6.4: Path vacío
    @patch('src.ssh_ru')
    def test_empty_path_handling(self, mock_ssh):
        """Test: Manejo de path vacío"""
        with patch('src.load_loopbacks') as mock_load:
            mock_load.return_value = self.expected_loopbacks
            mock_ssh.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")
            
            with patch('argparse.ArgumentParser.parse_args') as mock_parse:
                mock_parse.return_value = argparse.Namespace(
                    dest_prefix='fd00:0:2::1/64',
                    path_json='[]',  # Path vacío
                    replace=False,
                    high_occupancy=False
                )
                
                # Debería manejar el caso sin crash
                try:
                    main()
                except IndexError:
                    self.fail("main() no manejó correctamente un path vacío")
    
    # Test 6.5: Path con un solo nodo
    @patch('src.ssh_ru')
    def test_single_node_path(self, mock_ssh):
        """Test: Path con un solo nodo"""
        with patch('src.load_loopbacks') as mock_load:
            mock_load.return_value = self.expected_loopbacks
            mock_ssh.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")
            
            with patch('argparse.ArgumentParser.parse_args') as mock_parse:
                mock_parse.return_value = argparse.Namespace(
                    dest_prefix='fd00:0:2::1/64',
                    path_json='["ru"]',  # Solo un nodo
                    replace=False,
                    high_occupancy=False
                )
                
                # La construcción de segmentos debería manejar esto
                main()
                
                # Verificar que se construyó un comando válido
                ssh_calls = [call[0][0] for call in mock_ssh.call_args_list]
                route_calls = [call for call in ssh_calls if "route" in call]
                # Con un solo nodo, no hay segmentos intermedios pero debe crear comando
                self.assertTrue(len(route_calls) > 0)
    
    # Test 6.6: Múltiples rutas para verificar método correcto
    @patch('src.route_exists_for_dest')
    @patch('src.load_loopbacks')
    @patch('src.ssh_ru')
    def test_method_determination_logic(self, mock_ssh, mock_load, mock_route_exists):
        """Test: Lógica de determinación del método add/replace"""
        mock_load.return_value = self.expected_loopbacks
        mock_ssh.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")
        
        # Caso 1: ruta no existe, no flag replace -> add
        mock_route_exists.return_value = False
        with patch('argparse.ArgumentParser.parse_args') as mock_parse:
            mock_parse.return_value = argparse.Namespace(
                dest_prefix='fd00:0:2::1/64',
                path_json='["ru", "r1", "rg"]',
                replace=False,
                high_occupancy=False
            )
            main()
        
        ssh_calls = [call[0][0] for call in mock_ssh.call_args_list]
        self.assertTrue(any("route add" in call for call in ssh_calls))
        
        # Reset mock
        mock_ssh.reset_mock()
        
        # Caso 2: ruta existe, no flag replace -> replace
        mock_route_exists.return_value = True
        with patch('argparse.ArgumentParser.parse_args') as mock_parse:
            mock_parse.return_value = argparse.Namespace(
                dest_prefix='fd00:0:2::1/64',
                path_json='["ru", "r1", "rg"]',
                replace=False,
                high_occupancy=False
            )
            main()
        
        ssh_calls = [call[0][0] for call in mock_ssh.call_args_list]
        self.assertTrue(any("route replace" in call for call in ssh_calls))
        
        # Reset mock
        mock_ssh.reset_mock()
        
        # Caso 3: ruta no existe, flag replace -> replace
        mock_route_exists.return_value = False
        with patch('argparse.ArgumentParser.parse_args') as mock_parse:
            mock_parse.return_value = argparse.Namespace(
                dest_prefix='fd00:0:2::1/64',
                path_json='["ru", "r1", "rg"]',
                replace=True,
                high_occupancy=False
            )
            main()
        
        ssh_calls = [call[0][0] for call in mock_ssh.call_args_list]
        self.assertTrue(any("route replace" in call for call in ssh_calls))


class TestIntegration(TestSrcNoTables):
    """Tests de integración end-to-end"""
    
    # Test 7.1: Flujo completo nuevo
    @patch('src.load_loopbacks')
    @patch('src.ssh_ru')
    @patch('src.route_exists_for_dest')
    def test_complete_workflow_new_flow(self, mock_route_exists, mock_ssh, mock_load):
        """Test: Flujo completo para nuevo flujo"""
        # Setup
        mock_load.return_value = self.expected_loopbacks
        mock_route_exists.return_value = False
        mock_ssh.return_value = MagicMock(returncode=0, stdout=b"ok", stderr=b"")
        
        # Execute
        with patch('argparse.ArgumentParser.parse_args') as mock_parse:
            mock_parse.return_value = argparse.Namespace(
                dest_prefix='fd00:0:2::1/64',
                path_json='["ru", "r1", "r2", "rg"]',
                replace=False,
                high_occupancy=False
            )
            main()
        
        # Verify: Debe realizar solo una operación (instalar ruta)
        self.assertEqual(mock_ssh.call_count, 1)
        
        # Verificar contenido de la llamada (sin /64)
        call = mock_ssh.call_args[0][0]
        self.assertIn("route add", call)
        self.assertIn("fd00:0:2::1", call)
        self.assertIn("encap seg6", call)
        self.assertNotIn("/64", call)  # No debe aparecer máscara
    
    # Test 7.2: Flujo completo actualización
    @patch('src.load_loopbacks')
    @patch('src.ssh_ru')
    @patch('src.route_exists_for_dest')
    def test_complete_workflow_update_flow(self, mock_route_exists, mock_ssh, mock_load):
        """Test: Flujo completo para actualización de flujo existente"""
        # Setup
        mock_load.return_value = self.expected_loopbacks
        mock_route_exists.return_value = True  # Ruta ya existe
        mock_ssh.return_value = MagicMock(returncode=0, stdout=b"ok", stderr=b"")
        
        # Execute
        with patch('argparse.ArgumentParser.parse_args') as mock_parse:
            mock_parse.return_value = argparse.Namespace(
                dest_prefix='fd00:0:2::1/64',
                path_json='["ru", "r2", "r3", "rg"]',
                replace=False,
                high_occupancy=False
            )
            main()
        
        # Verify
        call = mock_ssh.call_args[0][0]
        
        # Debe reemplazar ruta existente (sin /64)
        self.assertIn("route replace", call)
        self.assertIn("fd00:0:2::1", call)
        self.assertNotIn("/64", call)  # Sin máscara


class TestDebugOutput(TestSrcNoTables):
    """Tests para salida de debug"""
    
    # Test 8.1: Formato de salida
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
                replace=False,
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