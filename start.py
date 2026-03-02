"""
Script de démarrage pour Railway et autres plateformes (PORT injecté en variable d'environnement).
"""
import os
import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
    )
