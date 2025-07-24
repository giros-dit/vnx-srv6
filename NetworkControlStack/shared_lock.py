#!/usr/bin/env python3
import fcntl
import os
import time
import threading
import contextlib

class SharedFileLock:
    """
    Lock compartido basado en archivo para coordinar operaciones S3
    entre app.py y pce.py en el mismo pod
    """
    def __init__(self, lock_file_path="/tmp/s3_operations.lock"):
        self.lock_file_path = lock_file_path
        self.local_lock = threading.RLock()
        self.file_handle = None
        
    def acquire(self, timeout=30):
        """Adquiere el lock con timeout"""
        start_time = time.time()
        
        # Primero adquirir lock local del thread
        if not self.local_lock.acquire(blocking=True, timeout=timeout):
            return False
            
        try:
            while time.time() - start_time < timeout:
                try:
                    # Abrir/crear archivo de lock
                    self.file_handle = open(self.lock_file_path, 'w')
                    
                    # Intentar lock exclusivo no bloqueante
                    fcntl.flock(self.file_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    
                    # Escribir PID para debugging
                    self.file_handle.write(f"{os.getpid()}\n")
                    self.file_handle.flush()
                    
                    return True
                    
                except (IOError, OSError):
                    # Lock ocupado, limpiar y reintentar
                    if self.file_handle:
                        try:
                            self.file_handle.close()
                        except:
                            pass
                        self.file_handle = None
                    
                    time.sleep(0.1)  # Esperar antes de reintentar
                    
            # Timeout alcanzado
            self.local_lock.release()
            return False
            
        except Exception as e:
            # Error inesperado, limpiar
            if self.file_handle:
                try:
                    self.file_handle.close()
                except:
                    pass
                self.file_handle = None
            self.local_lock.release()
            raise e
    
    def release(self):
        """Libera el lock"""
        try:
            if self.file_handle:
                try:
                    fcntl.flock(self.file_handle.fileno(), fcntl.LOCK_UN)
                    self.file_handle.close()
                except:
                    pass
                finally:
                    self.file_handle = None
            
            # Intentar eliminar archivo de lock
            try:
                os.unlink(self.lock_file_path)
            except:
                pass
                
        finally:
            self.local_lock.release()

# Lock global compartido para operaciones S3
s3_shared_lock = SharedFileLock()

@contextlib.contextmanager
def acquire_s3_lock(timeout=30):
    """
    Context manager para adquirir lock compartido S3
    """
    acquired = s3_shared_lock.acquire(timeout=timeout)
    if not acquired:
        raise RuntimeError(f"No se pudo adquirir lock S3 en {timeout}s")
    
    try:
        yield
    finally:
        s3_shared_lock.release()
