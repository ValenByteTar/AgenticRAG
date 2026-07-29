"""Knowledge Builder — index-time Knowledge Compiler (RES-002).

Arquitectura:

    Front-end (extractors) -> KIR -> Passes -> Validation -> Knowledge Model
        -> Back-end (codegen) -> Publish (Artifact Registry)

El Builder compila conocimiento existente sin LLM en E3.
El LLM es un extractor opcional e intercambiable (E5).
"""
