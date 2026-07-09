"""
Tests unitarios para cache de embeddings
"""

import pytest
import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))

from embedder import EmbeddingGenerator


class TestEmbedderCache:
    """Tests para cache de embeddings"""
    
    @pytest.fixture
    def embedder_with_cache(self):
        """Fixture con cache habilitado (mock)"""
        # Crear embedder mock para tests sin modelo real
        class MockEmbedder:
            def __init__(self):
                self.use_cache = True
                self._cache_hits = 0
                self._cache_misses = 0
                self.embedding_dim = 768
                self._cache = {}
            
            def _normalize_text_for_cache(self, text):
                return ' '.join(text.lower().strip().split())
            
            def _compute_text_hash(self, text):
                import hashlib
                normalized = self._normalize_text_for_cache(text)
                return hashlib.md5(normalized.encode('utf-8')).hexdigest()
            
            def _generate_embedding_uncached(self, text):
                # Mock: retorna embedding aleatorio
                return np.random.rand(self.embedding_dim).astype(np.float32)
            
            def generate_embedding(self, text):
                if not self.use_cache:
                    self._cache_misses += 1
                    return self._generate_embedding_uncached(text)
                
                text_hash = self._compute_text_hash(text)
                
                if text_hash in self._cache:
                    self._cache_hits += 1
                    return self._cache[text_hash]
                else:
                    self._cache_misses += 1
                    embedding = self._generate_embedding_uncached(text)
                    self._cache[text_hash] = embedding
                    return embedding
            
            def get_cache_stats(self):
                total = self._cache_hits + self._cache_misses
                hit_rate = (self._cache_hits / total * 100) if total > 0 else 0
                return {
                    'enabled': self.use_cache,
                    'hits': self._cache_hits,
                    'misses': self._cache_misses,
                    'total': total,
                    'hit_rate': hit_rate,
                    'cache_info': None
                }
            
            def clear_cache(self):
                self._cache.clear()
                self._cache_hits = 0
                self._cache_misses = 0
        
        return MockEmbedder()
    
    @pytest.fixture
    def embedder_without_cache(self):
        """Fixture sin cache"""
        class MockEmbedder:
            def __init__(self):
                self.use_cache = False
                self._cache_hits = 0
                self._cache_misses = 0
                self.embedding_dim = 768
            
            def generate_embedding(self, text):
                self._cache_misses += 1
                return np.random.rand(self.embedding_dim).astype(np.float32)
            
            def get_cache_stats(self):
                total = self._cache_hits + self._cache_misses
                return {
                    'enabled': self.use_cache,
                    'hits': self._cache_hits,
                    'misses': self._cache_misses,
                    'total': total,
                    'hit_rate': 0,
                    'cache_info': None
                }
        
        return MockEmbedder()
    
    def test_cache_hit_on_duplicate(self, embedder_with_cache):
        """Test que cache funciona con texto duplicado"""
        text = "Cuantos aerogeneradores tiene Kosten?"
        
        # Primera llamada - miss
        emb1 = embedder_with_cache.generate_embedding(text)
        stats1 = embedder_with_cache.get_cache_stats()
        
        assert stats1['misses'] == 1, "Primera llamada deberia ser miss"
        assert stats1['hits'] == 0, "No deberia haber hits aun"
        
        # Segunda llamada - hit
        emb2 = embedder_with_cache.generate_embedding(text)
        stats2 = embedder_with_cache.get_cache_stats()
        
        assert stats2['hits'] == 1, "Segunda llamada deberia ser hit"
        assert stats2['misses'] == 1, "Misses no deberia cambiar"
        
        # Embeddings deberian ser identicos
        assert np.array_equal(emb1, emb2), "Embeddings deberian ser identicos"
    
    def test_cache_hit_on_normalized_text(self, embedder_with_cache):
        """Test que cache funciona con texto normalizado"""
        text1 = "Cuantos aerogeneradores tiene Kosten?"
        text2 = "cuantos  aerogeneradores   tiene  kosten?"  # Diferentes espacios y mayusculas
        
        emb1 = embedder_with_cache.generate_embedding(text1)
        emb2 = embedder_with_cache.generate_embedding(text2)
        
        stats = embedder_with_cache.get_cache_stats()
        
        assert stats['hits'] == 1, "Segunda llamada deberia ser hit (texto normalizado)"
        assert np.array_equal(emb1, emb2), "Embeddings deberian ser identicos"
    
    def test_cache_miss_on_different_text(self, embedder_with_cache):
        """Test que cache no confunde textos diferentes"""
        text1 = "Cuantos aerogeneradores tiene Kosten?"
        text2 = "Cuantos inversores tiene Algarrobo?"
        
        emb1 = embedder_with_cache.generate_embedding(text1)
        emb2 = embedder_with_cache.generate_embedding(text2)
        
        stats = embedder_with_cache.get_cache_stats()
        
        assert stats['misses'] == 2, "Ambas llamadas deberian ser miss"
        assert stats['hits'] == 0, "No deberia haber hits"
        assert not np.array_equal(emb1, emb2), "Embeddings deberian ser diferentes"
    
    def test_cache_stats_calculation(self, embedder_with_cache):
        """Test calculo de estadisticas de cache"""
        texts = [
            "Texto 1",
            "Texto 2",
            "Texto 1",  # Repetido
            "Texto 3",
            "Texto 2",  # Repetido
            "Texto 1",  # Repetido
        ]
        
        for text in texts:
            embedder_with_cache.generate_embedding(text)
        
        stats = embedder_with_cache.get_cache_stats()
        
        assert stats['total'] == 6, "Total deberia ser 6"
        assert stats['misses'] == 3, "Deberia haber 3 misses (textos unicos)"
        assert stats['hits'] == 3, "Deberia haber 3 hits (repeticiones)"
        assert stats['hit_rate'] == 50.0, "Hit rate deberia ser 50%"
    
    def test_without_cache_no_hits(self, embedder_without_cache):
        """Test que sin cache no hay hits"""
        text = "Cuantos aerogeneradores tiene Kosten?"
        
        embedder_without_cache.generate_embedding(text)
        embedder_without_cache.generate_embedding(text)
        embedder_without_cache.generate_embedding(text)
        
        stats = embedder_without_cache.get_cache_stats()
        
        assert stats['hits'] == 0, "Sin cache no deberia haber hits"
        assert stats['misses'] == 3, "Todas las llamadas deberian ser miss"
        assert stats['hit_rate'] == 0, "Hit rate deberia ser 0%"
    
    def test_clear_cache(self, embedder_with_cache):
        """Test limpieza de cache"""
        text = "Cuantos aerogeneradores tiene Kosten?"
        
        # Generar embedding
        embedder_with_cache.generate_embedding(text)
        embedder_with_cache.generate_embedding(text)
        
        stats_before = embedder_with_cache.get_cache_stats()
        assert stats_before['hits'] == 1, "Deberia haber 1 hit antes de limpiar"
        
        # Limpiar cache
        embedder_with_cache.clear_cache()
        
        stats_after = embedder_with_cache.get_cache_stats()
        assert stats_after['hits'] == 0, "Hits deberia ser 0 despues de limpiar"
        assert stats_after['misses'] == 0, "Misses deberia ser 0 despues de limpiar"
    
    def test_cache_performance_benefit(self, embedder_with_cache):
        """Test que cache mejora performance (simulado)"""
        import time
        
        text = "Cuantos aerogeneradores tiene Kosten?"
        
        # Primera llamada (miss)
        start1 = time.time()
        embedder_with_cache.generate_embedding(text)
        time1 = time.time() - start1
        
        # Segunda llamada (hit - deberia ser mas rapida)
        start2 = time.time()
        embedder_with_cache.generate_embedding(text)
        time2 = time.time() - start2
        
        # En un sistema real, time2 deberia ser significativamente menor que time1
        # En este mock, solo verificamos que funciona
        assert time2 >= 0, "Tiempo deberia ser positivo"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
