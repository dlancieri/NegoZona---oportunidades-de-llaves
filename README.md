# MVP de oportunidades de llaves de negocios

Este proyecto recorre los anuncios de llaves de negocios de NegoZona, los ordena para decidir a quién contactar y genera un informe HTML junto con archivos CSV.

La puntuación es preliminar: evalúa el aviso y el encaje operativo. La rentabilidad real solo se calcula después de obtener y verificar ventas, utilidad, alquiler, personal y dedicación del propietario.

## Archivos

- `llaves_negocios.py`: extractor, puntuación y generación del informe.
- `requirements_llaves.txt`: dependencias.
- `.github/workflows/llaves.yml`: ejecución automática lunes y jueves.
- `estado_llaves.csv`: seguimiento manual de cada anuncio.
- `historial_anuncios.csv`: lo crea el primer proceso y permite detectar anuncios nuevos, retirados o con cambios de precio.

La selección se hace en dos etapas. Primero descarta negocios incompatibles con el perfil: gastronomía, oficios personales, indumentaria, coordinación logística, negocios sin actividad, zonas fuera de Montevideo/Canelones/Maldonado y precios mayores al presupuesto. Después ordena los restantes por modelo físico, evidencia de funcionamiento, delegabilidad e información económica.

Los resultados quedan separados en:

- `top_contactar.csv`: Prioridad A, alineados con el perfil.
- `revisar_manual.csv`: Prioridad B y seguimientos ya iniciados.
- `no_alineados.csv`: descartados por perfil, zona, presupuesto o estado.

## Incorporarlo al repositorio existente

Copiar el contenido de esta carpeta a la raíz del repositorio usado para el automatizador inmobiliario. Los nombres son diferentes, por lo que no reemplaza `main.py` ni su workflow.

Después, abrir **Actions → NegoZona - oportunidades de llaves → Run workflow**. Al finalizar, descargar el artefacto `resultados-negozona-N`.

Si el paso que guarda el historial no tiene permisos, habilitar en GitHub: **Settings → Actions → General → Workflow permissions → Read and write permissions**.

## Seguimiento manual

Editar `estado_llaves.csv` usando estas columnas:

```csv
external_id,estado,fecha,notas
976,sin respuesta,2026-08-24,Se envió consulta inicial
```

Estados sugeridos: `contactado`, `respondió`, `sin respuesta`, `vendido`, `descartado` y `no disponible`.

## Ajustes

El workflow incluye tres variables editables:

- `NEGOZONA_SCOPE`: `uruguay` o `montevideo`.
- `TARGET_BUDGET_USD`: presupuesto objetivo usado por el score.
- `MAX_PAGES`: máximo de páginas a recorrer.

## Prueba local con un HTML guardado

```bash
pip install -r requirements_llaves.txt
python llaves_negocios.py --html "Llave de Negocios en venta en NegoZona Uruguay.htm"
```
