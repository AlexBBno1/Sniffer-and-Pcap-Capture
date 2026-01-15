"""
Cache Layer
===========
Caching for expensive operations to improve performance.
"""

import time
import threading
from typing import Any, Optional, Callable
from datetime import datetime

from .config import CONNECTION_CACHE_TTL, INTERFACE_CACHE_TTL


class CacheEntry:
    """Single cache entry with TTL"""
    
    def __init__(self, value: Any, ttl: float):
        self.value = value
        self.created_at = time.time()
        self.ttl = ttl
    
    def is_valid(self) -> bool:
        """Check if cache entry is still valid"""
        return time.time() - self.created_at < self.ttl


class StatusCache:
    """
    Cache for expensive operations like connection tests and interface detection.
    
    Features:
    - TTL-based expiration
    - Thread-safe access
    - Lazy refresh on access
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """Singleton pattern"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self._cache: dict[str, CacheEntry] = {}
        self._cache_lock = threading.Lock()
        
        # Cache TTL settings (in seconds) - using config values
        self._ttl_settings = {
            'connection_status': CONNECTION_CACHE_TTL,  # Default 10s (was 5s)
            'interface_mapping': INTERFACE_CACHE_TTL,   # Default 300s (5 minutes)
            'wifi_config': 60,           # WiFi config cache for 1 minute
            'time_info': 2,              # Time info cache for 2 seconds
        }
        
        self._initialized = True
    
    def get(self, key: str) -> Optional[Any]:
        """
        Get cached value if still valid.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if expired/missing
        """
        with self._cache_lock:
            entry = self._cache.get(key)
            if entry and entry.is_valid():
                return entry.value
            return None
    
    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        """
        Set cache value.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds (uses default if not specified)
        """
        if ttl is None:
            ttl = self._ttl_settings.get(key, 30)
        
        with self._cache_lock:
            self._cache[key] = CacheEntry(value, ttl)
    
    def invalidate(self, key: str) -> None:
        """Invalidate a specific cache entry"""
        with self._cache_lock:
            if key in self._cache:
                del self._cache[key]
    
    def invalidate_all(self) -> None:
        """Invalidate all cache entries"""
        with self._cache_lock:
            self._cache.clear()
    
    def get_or_compute(self, key: str, compute_fn: Callable, ttl: Optional[float] = None) -> Any:
        """
        Get cached value or compute and cache if missing/expired.
        
        Args:
            key: Cache key
            compute_fn: Function to compute value if not cached
            ttl: Time-to-live in seconds
            
        Returns:
            Cached or computed value
        """
        cached = self.get(key)
        if cached is not None:
            return cached
        
        # Compute new value
        value = compute_fn()
        self.set(key, value, ttl)
        return value


# Global singleton instance
status_cache = StatusCache()


# Convenience functions for common cache operations
def get_cached_connection_status() -> Optional[bool]:
    """Get cached connection status"""
    return status_cache.get('connection_status')


def set_cached_connection_status(connected: bool) -> None:
    """Cache connection status"""
    status_cache.set('connection_status', connected)


def get_cached_interface_mapping() -> Optional[dict]:
    """Get cached interface mapping"""
    return status_cache.get('interface_mapping')


def set_cached_interface_mapping(mapping: dict) -> None:
    """Cache interface mapping"""
    status_cache.set('interface_mapping', mapping)


def invalidate_connection_cache() -> None:
    """Invalidate connection-related caches"""
    status_cache.invalidate('connection_status')
    status_cache.invalidate('interface_mapping')
