from __future__ import annotations

import argparse
import html
import os
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import pandas as pd
from lxml import html as lxml_html
from lxml.html import HtmlElement


BASE_URL = "https://negozona.com.uy"
SEARCH_URLS = {
    "uruguay": (
        f"{BASE_URL}/anuncios/Busqueda/Comercios/Todos/Todos/Todos/"
        "Todos/Todos/Todos/Todos/Todos"
    ),
    "montevideo": (
        f"{BASE_URL}/anuncios/Busqueda/Comercios/State-2-Montevideo/Todos/"
        "Todos/Todos/Todos/Todos/0,100000+/Todos?order_by_field="
    ),
}

MAX_PAGES = int(os.getenv("MAX_PAGES", "10"))
TARGET_BUDGET_USD = int(os.getenv("TARGET_BUDGET_USD", "60000"))
SCOPE = os.getenv("NEGOZONA_SCOPE", "uruguay").strip().lower()

OUTPUT_ALL = "negocios_negozona.csv"
OUTPUT_CONTACT = "top_contactar.csv"
OUTPUT_REVIEW = "revisar_manual.csv"
OUTPUT_NOT_ALIGNED = "no_alineados.csv"
OUTPUT_CHANGES = "cambios_detectados.csv"
OUTPUT_HISTORY = "historial_anuncios.csv"
OUTPUT_REPORT = "informe_llaves.html"
MANUAL_STATE = "estado_llaves.csv"

FINANCIAL_SIGNALS = {
    "facturacion": 20,
    "ventas mensuales": 20,
    "venta mensual": 20,
    "ganancia": 25,
    "utilidad": 25,
    "rentabilidad": 15,
    "balance": 15,
    "comprobable": 15,
    "alquiler": 8,
    "contrato": 8,
    "empleados": 10,
    "personal": 10,
    "encargado": 15,
    "carga horaria": 15,
    "dedicacion del dueno": 15,
}

OPERATING_TERMS = {
    "pleno funcionamiento": 30,
    "en funcionamiento": 30,
    "funcionando": 30,
    "en marcha": 25,
    "en actividad": 25,
    "cartera de clientes": 20,
    "clientes fijos": 20,
    "trabajo fijo": 18,
    "facturacion": 15,
    "trayectoria": 12,
    "antiguedad": 12,
    "habilitado": 8,
    "habilitaciones": 8,
}

DELEGATION_TERMS = {
    "encargado": 35,
    "personal estable": 30,
    "empleados": 25,
    "operarios": 30,
    "equipo de trabajo": 25,
    "equipo formado": 25,
    "semi automatica": 25,
    "semiautomatica": 25,
    "automatizada": 30,
    "sin presencia del dueno": 40,
}

OWNER_DEPENDENCY_TERMS = (
    "atendido por su dueno",
    "autoempleo",
    "se tu propio jefe",
    "solo de ponerse a trabajar",
    "trabajarlo uno mismo",
    "servicio a domicilio",
)

RETAIL_TERMS = (
    "kiosco",
    "minimarket",
    "mini mercado",
    "bazar",
    "regaleria",
    "tienda de ropa",
    "local de ropa",
    "papeleria",
    "perfumeria",
    "ferreteria",
    "pet shop",
)

PARTNERSHIP_TERMS = (
    "venta del 50%",
    "venta de 50%",
    "participacion mayoritaria",
    "participacion societaria",
    "busca socio",
)


def now_uy() -> datetime:
    return datetime.now(ZoneInfo("America/Montevideo"))


def normalize_text(value: Any) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFD", text)
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return " ".join(text.lower().split())


def node_text(node: HtmlElement | None) -> str:
    return " ".join(" ".join(node.itertext()).split()) if node is not None else ""


def class_nodes(node: HtmlElement, class_name: str) -> list[HtmlElement]:
    return node.xpath(
        f'.//*[contains(concat(" ", normalize-space(@class), " "), " {class_name} ")]'
    )


def first_class(node: HtmlElement, class_name: str) -> HtmlElement | None:
    nodes = class_nodes(node, class_name)
    return nodes[0] if nodes else None


def parse_price(value: str) -> tuple[str, float | None]:
    normalized = value.upper().strip()
    currency = "USD" if "USD" in normalized or "U$S" in normalized else "UYU" if "$" in normalized else ""
    numeric = re.sub(r"[^\d.,]", "", normalized)
    if not numeric:
        return currency, None
    if "," in numeric and "." in numeric:
        numeric = numeric.replace(".", "").replace(",", ".")
    elif numeric.count(".") > 1 or ("." in numeric and len(numeric.rsplit(".", 1)[1]) == 3):
        numeric = numeric.replace(".", "")
    elif "," in numeric:
        numeric = numeric.replace(",", ".")
    try:
        return currency, float(numeric)
    except ValueError:
        return currency, None


def split_category(value: str) -> tuple[str, str, str]:
    parts = [part.strip() for part in value.split("|") if part.strip()]
    padded = (parts + ["", "", ""])[:3]
    return padded[0], padded[1], padded[2]


def extract_id(url: str, fallback: str = "") -> str:
    match = re.search(r"/anuncios/(\d+)(?:\D|$)", url)
    if match:
        return match.group(1)
    match = re.search(r"(\d+)", fallback)
    return match.group(1) if match else ""


def parse_card(card: HtmlElement, page_number: int) -> dict[str, Any] | None:
    link_nodes = card.xpath('.//a[contains(@href, "/anuncios/")]')
    link_node = link_nodes[0] if link_nodes else None
    if link_node is None or not link_node.get("href"):
        return None
    link = urljoin(BASE_URL, str(link_node.get("href")))
    external_id = extract_id(link, node_text(first_class(card, "id_publication")))
    if not external_id:
        return None

    category_text = node_text(first_class(card, "announcement_type_title"))
    ad_type, category, subcategory = split_category(category_text)
    price_text = node_text(first_class(card, "price_publication"))
    currency, price = parse_price(price_text)
    phone_nodes = card.xpath('.//a[starts-with(@href, "tel:")]')
    phone_node = phone_nodes[0] if phone_nodes else None
    phone = str(phone_node.get("href", "")).removeprefix("tel:").strip() if phone_node is not None else ""
    image_nodes = card.xpath(
        './/img[contains(concat(" ", normalize-space(@class), " "), " img_publication ")]'
    )
    image_node = image_nodes[0] if image_nodes else None

    row = {
        "fecha_extraccion": now_uy().strftime("%Y-%m-%d %H:%M:%S"),
        "fuente": "NegoZona",
        "pagina": page_number,
        "external_id": external_id,
        "titulo": node_text(first_class(card, "inner_title_publication")),
        "tipo_anuncio": ad_type,
        "categoria": category,
        "subcategoria": subcategory,
        "ubicacion": node_text(first_class(card, "item_data")),
        "descripcion": node_text(first_class(card, "description_publication")),
        "precio_texto": price_text,
        "moneda": currency,
        "precio": price,
        "precio_usd": price if currency == "USD" else None,
        "telefono": phone,
        "premium": bool(class_nodes(card, "ribbon")),
        "imagen": str(image_node.get("src", "")) if image_node is not None else "",
        "link": link,
    }
    row.update(score_listing(row))
    return row


def parse_listing_html(document: str, page_number: int) -> tuple[list[dict[str, Any]], str | None]:
    tree = lxml_html.fromstring(document)
    rows = []
    cards = tree.xpath(
        '//div[contains(concat(" ", normalize-space(@class), " "), " publication_default ")]'
    )
    for card in cards:
        parsed = parse_card(card, page_number)
        if parsed:
            rows.append(parsed)
    next_nodes = tree.xpath('//a[@rel="next"]')
    next_node = next_nodes[0] if next_nodes else None
    next_url = urljoin(BASE_URL, str(next_node.get("href"))) if next_node is not None and next_node.get("href") else None
    return rows, next_url


def contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def score_listing(row: dict[str, Any]) -> dict[str, Any]:
    full_text = normalize_text(
        " ".join(str(row.get(key) or "") for key in ("titulo", "categoria", "subcategoria", "ubicacion", "descripcion"))
    )
    category = normalize_text(row.get("categoria"))
    subcategory = normalize_text(row.get("subcategoria"))
    location = normalize_text(row.get("ubicacion"))
    description = str(row.get("descripcion") or "")
    price = row.get("precio_usd")

    # La información formal del aviso (teléfono, categoría, ubicación) ya no
    # compensa la falta de datos económicos. Este score mide información útil.
    information = 5 if price else 0
    information += 5 if len(description) >= 120 else 2 if len(description) >= 60 else 0
    financial_labels: list[str] = []
    for term, points in FINANCIAL_SIGNALS.items():
        if term in full_text:
            information += points
            financial_labels.append(term)

    model = 0
    model_labels: list[str] = []
    is_industry = category == "industria y manufactura"
    is_distribution = contains_any(full_text, ("distribucion", "distribuidora", "importadora", "mayorista", "b2b"))
    is_production = contains_any(full_text, ("fabrica", "fabricacion propia", "planta de elaboracion", "planta semi automatica", "planta semiautomatica"))
    is_laundry = contains_any(full_text, ("lavanderia", "lavadero de ropas", "lavadero de ropa"))
    is_medical_equipment = contains_any(full_text, ("equipos medicos", "equipamiento medico"))
    has_machinery = contains_any(full_text, ("maquinaria", "maquinas", "equipamiento", "totalmente equipado", "infraestructura"))
    has_recurring_customers = contains_any(full_text, ("cartera de clientes", "clientes fijos", "trabajo fijo", "contratos vigentes"))

    if is_industry:
        model += 30
        model_labels.append("industria/manufactura")
    if is_production:
        model += 35
        model_labels.append("producción propia")
    if is_distribution:
        model += 30
        model_labels.append("distribución/importación")
    if is_laundry:
        model += 30
        model_labels.append("servicio recurrente de lavandería")
    if is_medical_equipment:
        model += 20
        model_labels.append("equipamiento médico")
    if "taller" in full_text:
        model += 12
        model_labels.append("taller")
    if has_machinery:
        model += 10
        model_labels.append("activos físicos")
    if has_recurring_customers:
        model += 18
        model_labels.append("clientes o contratos recurrentes")

    operation = 0
    operation_labels: list[str] = []
    for term, points in OPERATING_TERMS.items():
        if term in full_text:
            operation += points
            operation_labels.append(term)
    if re.search(r"\b(?:[5-9]|[1-9]\d)\s+anos\b", full_text):
        operation += 12
        operation_labels.append("antigüedad declarada")
    if has_machinery:
        operation += 8

    delegation = 15
    delegation_labels: list[str] = []
    for term, points in DELEGATION_TERMS.items():
        if term in full_text:
            delegation += points
            delegation_labels.append(term)
    if is_industry:
        delegation += 10
    if contains_any(full_text, OWNER_DEPENDENCY_TERMS):
        delegation -= 35
        delegation_labels.append("posible autoempleo")

    is_gastronomy = category == "gastronomia"
    is_personal_skill = contains_any(
        f"{category} {subcategory} {full_text}",
        ("peluquer", "manicure", "centro de estetica", "optica", "salon de belleza"),
    )
    is_clothing = category == "indumentaria y moda"
    is_retail = contains_any(full_text, RETAIL_TERMS)
    is_logistics_coordination = contains_any(full_text, ("coordinacion y transporte", "transporte logistico remoto"))
    is_partnership = contains_any(full_text, PARTNERSHIP_TERMS)
    is_franchise = "franquicia" in full_text
    inactive = contains_any(full_text, ("sin actividad", "actualmente inactiva", "actualmente inactivo"))
    assets_only = contains_any(full_text, ("elementos para fabrica", "solo equipamiento", "venta de maquinaria"))

    risk = 0
    risk_labels: list[str] = []
    required_data = {
        "ventas/facturación": ("facturacion", "ventas mensuales", "venta mensual"),
        "utilidad neta": ("utilidad", "ganancia", "rentabilidad"),
        "alquiler y contrato": ("alquiler", "contrato"),
        "personal": ("empleados", "personal", "encargado"),
        "dedicación del dueño": ("dueno", "propietario", "carga horaria", "dedicacion"),
    }
    missing = []
    for label, terms in required_data.items():
        if not contains_any(full_text, terms):
            missing.append(label)
    risk += 5 * len(missing)
    if not price:
        risk += 15
        risk_labels.append("sin precio publicado")
    if len(description) < 60:
        risk += 10
        risk_labels.append("descripción escasa")
    if contains_any(full_text, ("temporada", "estacional")):
        risk += 15
        risk_labels.append("posible estacionalidad")
    if is_partnership:
        risk += 25
        risk_labels.append("compra parcial o socio")
    if is_retail:
        risk += 20
        risk_labels.append("comercio minorista con presencia diaria")
    if is_franchise:
        risk += 15
        risk_labels.append("dependencia de franquicia")
    if delegation < 40:
        risk += 15
        risk_labels.append("delegabilidad no demostrada")

    allowed_location = contains_any(location, ("montevideo", "canelones", "maldonado"))
    hard_reason = ""
    if is_gastronomy:
        hard_reason = "Gastronomía: alta dedicación y horarios extensos"
    elif is_personal_skill:
        hard_reason = "Servicio dependiente de oficio o personal especializado"
    elif is_clothing:
        hard_reason = "Comercio minorista de indumentaria"
    elif is_logistics_coordination:
        hard_reason = "Coordinación logística, actividad que no buscás"
    elif inactive:
        hard_reason = "No compra flujo actual: el negocio está sin actividad"
    elif assets_only:
        hard_reason = "Venta de activos, no de un flujo funcionando"

    information = max(0, min(information, 100))
    model = max(0, min(model, 100))
    operation = max(0, min(operation, 100))
    delegation = max(0, min(delegation, 100))
    risk = max(0, min(risk, 100))
    raw_contact_score = (
        0.45 * model
        + 0.25 * operation
        + 0.15 * delegation
        + 0.15 * information
        - 0.20 * risk
    )
    contact_score = round(1.35 * raw_contact_score)
    if price:
        if 25_000 <= price <= 40_000:
            contact_score += 8
        elif price <= TARGET_BUDGET_USD:
            contact_score += 5
    if "montevideo" in location:
        contact_score += 5
    elif contains_any(location, ("canelones", "maldonado")):
        contact_score += 2
    contact_score = max(0, min(contact_score, 100))

    if hard_reason:
        alignment = "No alineado"
        recommendation = f"No alineado: {hard_reason}"
    elif not allowed_location:
        alignment = "Fuera de zona"
        recommendation = "Fuera de zona objetivo"
    elif price and price > TARGET_BUDGET_USD:
        alignment = "Fuera de presupuesto"
        recommendation = f"Fuera de presupuesto (más de USD {TARGET_BUDGET_USD:,})"
    elif is_partnership and model >= 30 and operation >= 20:
        alignment = "Dudoso"
        recommendation = "Prioridad B - solo si aceptás socio y falta validar control"
    elif is_retail and not (model >= 45 and operation >= 30 and delegation >= 40):
        alignment = "No alineado"
        recommendation = "No alineado: comercio minorista con alta presencia probable"
    elif model >= 50 and operation >= 30:
        alignment = "Alineado"
        recommendation = "Prioridad A - contactar"
    elif model >= 30 and operation >= 20:
        alignment = "Dudoso"
        recommendation = "Prioridad B - validar delegabilidad y caja"
    else:
        alignment = "No alineado"
        recommendation = "No alineado: no demuestra flujo delegable ni modelo compatible"

    questions = []
    question_map = {
        "ventas/facturación": "ventas promedio mensuales de los últimos 12 meses",
        "utilidad neta": "utilidad neta mensual, después de todos los costos",
        "alquiler y contrato": "alquiler actual, gastos y plazo restante del contrato",
        "personal": "cantidad de empleados, funciones y costo total mensual",
        "dedicación del dueño": "horas y tareas que realiza hoy el propietario",
    }
    for item in missing:
        questions.append(question_map[item])
    questions.extend([
        "qué activos y stock están incluidos en el precio",
        "si los números se pueden respaldar con documentación",
        "motivo concreto de la venta",
    ])
    short_questions = questions[:6]
    message = (
        f"Hola, estoy interesado en el anuncio {row.get('external_id')} ({row.get('titulo')}). "
        "Antes de coordinar una visita, ¿me podrías indicar "
        + "; ".join(short_questions)
        + "? Gracias."
    )

    return {
        "score_contacto": contact_score,
        "alineacion_perfil": alignment,
        "score_encaje": model,
        "score_modelo": model,
        "score_operacion": operation,
        "score_delegabilidad": delegation,
        "score_informacion": information,
        "score_senal_negocio": operation,
        "riesgo_preliminar": risk,
        "recomendacion": recommendation,
        "senales": " | ".join(sorted(set(model_labels + operation_labels + delegation_labels + financial_labels))),
        "datos_faltantes": " | ".join(missing),
        "alertas": " | ".join(sorted(set(risk_labels))) or "Sin alertas concluyentes en el aviso",
        "mensaje_contacto": message,
    }


def scrape_live(scope: str) -> list[dict[str, Any]]:
    from playwright.sync_api import sync_playwright

    if scope not in SEARCH_URLS:
        raise ValueError(f"Alcance inválido: {scope}. Usar uruguay o montevideo.")
    rows: list[dict[str, Any]] = []
    visited: set[str] = set()
    next_url: str | None = SEARCH_URLS[scope]

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": 1440, "height": 1000},
            locale="es-UY",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
            ),
        )
        page_number = 1
        while next_url and page_number <= MAX_PAGES and next_url not in visited:
            visited.add(next_url)
            print(f"Página {page_number}: {next_url}")
            page.goto(next_url, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_selector("div.publication_default", timeout=30_000)
            page.wait_for_timeout(1_000)
            page_rows, next_url = parse_listing_html(page.content(), page_number)
            print(f"  Anuncios encontrados: {len(page_rows)}")
            rows.extend(page_rows)
            page_number += 1
        browser.close()
    return rows


def scrape_saved_html(paths: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for page_number, raw_path in enumerate(paths, start=1):
        path = Path(raw_path)
        document = path.read_text(encoding="utf-8", errors="replace")
        page_rows, _ = parse_listing_html(document, page_number)
        print(f"Archivo {path.name}: {len(page_rows)} anuncios")
        rows.extend(page_rows)
    return rows


def load_manual_state() -> pd.DataFrame:
    path = Path(MANUAL_STATE)
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame(columns=["external_id", "estado", "fecha", "notas"])
    state = pd.read_csv(path, dtype={"external_id": str}).fillna("")
    for column in ("external_id", "estado", "fecha", "notas"):
        if column not in state.columns:
            state[column] = ""
    return state[["external_id", "estado", "fecha", "notas"]]


def apply_manual_state(df: pd.DataFrame) -> pd.DataFrame:
    state = load_manual_state().rename(columns={"fecha": "fecha_estado", "notas": "notas_estado"})
    df = df.drop(columns=["estado", "fecha_estado", "notas_estado"], errors="ignore")
    df["external_id"] = df["external_id"].astype(str)
    df = df.merge(state, on="external_id", how="left")
    for column in ("estado", "fecha_estado", "notas_estado"):
        df[column] = df[column].fillna("")

    closed = {"vendido", "descartado", "no disponible"}
    no_reply = {"sin respuesta", "no respondio", "no respondió"}
    for index, row in df.iterrows():
        state_value = normalize_text(row["estado"])
        if state_value in closed:
            df.at[index, "recomendacion"] = f"Excluir: {row['estado']}"
            df.at[index, "score_contacto"] = 0
        elif state_value in no_reply:
            df.at[index, "recomendacion"] = "Seguimiento pendiente"
            df.at[index, "score_contacto"] = max(0, int(row["score_contacto"]) - 8)
        elif state_value in {"respondio", "respondió"}:
            df.at[index, "recomendacion"] = "Analizar respuesta"
    return df


def build_changes(current: pd.DataFrame) -> pd.DataFrame:
    path = Path(OUTPUT_HISTORY)
    if not path.exists() or path.stat().st_size == 0:
        changes = current[["external_id", "titulo", "precio_usd", "link"]].copy()
        changes.insert(0, "cambio", "nuevo")
        changes["precio_anterior_usd"] = None
        return changes

    previous = pd.read_csv(path, dtype={"external_id": str}).fillna("")
    if "precio_usd" not in previous.columns:
        previous["precio_usd"] = None
    old = previous.set_index("external_id")
    rows = []
    current_ids = set(current["external_id"].astype(str))
    for _, item in current.iterrows():
        external_id = str(item["external_id"])
        if external_id not in old.index:
            rows.append({
                "cambio": "nuevo", "external_id": external_id, "titulo": item["titulo"],
                "precio_anterior_usd": None, "precio_usd": item["precio_usd"], "link": item["link"],
            })
            continue
        previous_price = pd.to_numeric(old.loc[external_id, "precio_usd"], errors="coerce")
        current_price = pd.to_numeric(item["precio_usd"], errors="coerce")
        if pd.notna(previous_price) and pd.notna(current_price) and previous_price != current_price:
            rows.append({
                "cambio": "cambio de precio", "external_id": external_id, "titulo": item["titulo"],
                "precio_anterior_usd": previous_price, "precio_usd": current_price, "link": item["link"],
            })
    for external_id in set(old.index.astype(str)) - current_ids:
        item = old.loc[external_id]
        rows.append({
            "cambio": "ya no aparece", "external_id": external_id,
            "titulo": item.get("titulo", ""), "precio_anterior_usd": item.get("precio_usd", None),
            "precio_usd": None, "link": item.get("link", ""),
        })
    return pd.DataFrame(rows, columns=[
        "cambio", "external_id", "titulo", "precio_anterior_usd", "precio_usd", "link"
    ])


def safe_cell(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return html.escape(str(value))


def generate_report(df: pd.DataFrame, changes: pd.DataFrame) -> None:
    active = df[
        df["recomendacion"].astype(str).str.startswith(("Prioridad A", "Prioridad B"))
        | df["recomendacion"].isin(["Seguimiento pendiente", "Analizar respuesta"])
    ].copy()
    cards = []
    for _, row in active.sort_values("score_contacto", ascending=False).head(40).iterrows():
        price = safe_cell(row.get("precio_texto")) or "Precio no publicado"
        cards.append(f"""
        <article class="card">
          <div class="top"><span class="score">{safe_cell(row.get('score_contacto'))}</span>
          <div><h2>{safe_cell(row.get('titulo'))}</h2><p>{safe_cell(row.get('ubicacion'))} · {price}</p></div></div>
          <div class="metrics">
            <div><b>Acción</b><br>{safe_cell(row.get('recomendacion'))}</div>
            <div><b>Modelo</b><br>{safe_cell(row.get('score_modelo'))}/100</div>
            <div><b>Operación real</b><br>{safe_cell(row.get('score_operacion'))}/100</div>
            <div><b>Delegabilidad</b><br>{safe_cell(row.get('score_delegabilidad'))}/100</div>
            <div><b>Riesgo preliminar</b><br>{safe_cell(row.get('riesgo_preliminar'))}/100</div>
          </div>
          <p><b>Rubro:</b> {safe_cell(row.get('categoria'))} / {safe_cell(row.get('subcategoria'))}</p>
          <p>{safe_cell(row.get('descripcion'))}</p>
          <p><b>Señales:</b> {safe_cell(row.get('senales')) or 'Sin señales concluyentes'}</p>
          <p><b>Datos a pedir:</b> {safe_cell(row.get('datos_faltantes'))}</p>
          <details><summary>Mensaje sugerido</summary><p>{safe_cell(row.get('mensaje_contacto'))}</p></details>
          <p><a href="{safe_cell(row.get('link'))}">Abrir anuncio</a></p>
        </article>
        """)
    new_count = int((changes.get("cambio", pd.Series(dtype=str)) == "nuevo").sum())
    document = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Oportunidades de llaves de negocios</title><style>
body{{font-family:Arial,sans-serif;background:#f3f5f7;color:#1f2933;margin:0;padding:24px}}main{{max-width:1050px;margin:auto}}
.summary,.card{{background:white;border-radius:14px;padding:22px;margin:16px 0;box-shadow:0 3px 14px #00000012}}
.top{{display:flex;gap:16px;align-items:center}}.score{{display:grid;place-items:center;min-width:58px;height:58px;border-radius:50%;background:#173f5f;color:white;font-size:22px;font-weight:bold}}
h2{{margin:0 0 4px}}p{{line-height:1.5}}.metrics{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px;margin:18px 0}}
.metrics div{{background:#f4f7f9;border-radius:9px;padding:11px}}a{{color:#0b65a5;font-weight:bold}}summary{{cursor:pointer;font-weight:bold}}
</style></head><body><main><h1>Llaves de negocios priorizadas</h1>
<div class="summary"><b>{len(active)}</b> anuncios alineados o dudosos · <b>{new_count}</b> nuevos o sin historial.<br>
Generado {safe_cell(now_uy().strftime('%Y-%m-%d %H:%M'))}. Solo se muestran operaciones físicas con flujo aparente y posibilidad de gestión; los descartados quedan en el CSV general.</div>
{''.join(cards) if cards else '<p>Sin anuncios activos.</p>'}</main></body></html>"""
    Path(OUTPUT_REPORT).write_text(document, encoding="utf-8")


def write_outputs(rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise RuntimeError("No se extrajeron anuncios; no se reemplaza el historial.")
    df = pd.DataFrame(rows).drop_duplicates(subset=["external_id"], keep="first")
    df = apply_manual_state(df)
    df = df.sort_values(["score_contacto", "precio_usd"], ascending=[False, True], na_position="last")
    changes = build_changes(df)

    df.to_csv(OUTPUT_ALL, index=False)
    changes.to_csv(OUTPUT_CHANGES, index=False)
    contact = df[
        df["recomendacion"].astype(str).str.startswith("Prioridad A")
    ]
    review = df[
        df["recomendacion"].astype(str).str.startswith("Prioridad B")
        | df["recomendacion"].isin(["Seguimiento pendiente", "Analizar respuesta"])
    ]
    not_aligned = df[
        ~df.index.isin(contact.index)
        & ~df.index.isin(review.index)
    ]
    contact.to_csv(OUTPUT_CONTACT, index=False)
    review.to_csv(OUTPUT_REVIEW, index=False)
    not_aligned.to_csv(OUTPUT_NOT_ALIGNED, index=False)
    generate_report(df, changes)

    history_columns = [
        "fecha_extraccion", "external_id", "titulo", "precio_usd", "ubicacion",
        "categoria", "subcategoria", "link",
    ]
    df[history_columns].to_csv(OUTPUT_HISTORY, index=False)

    print("\nRESUMEN")
    print(f"Anuncios únicos: {len(df)}")
    print(f"Contactar: {len(contact)}")
    print(f"Revisar / seguimiento: {len(review)}")
    print(f"No alineados / fuera de alcance: {len(not_aligned)}")
    print(f"Cambios: {len(changes)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prioriza llaves de negocios publicadas en NegoZona.")
    parser.add_argument("--scope", choices=sorted(SEARCH_URLS), default=SCOPE)
    parser.add_argument("--html", action="append", default=[], help="HTML guardado para una prueba sin navegar.")
    args = parser.parse_args()
    rows = scrape_saved_html(args.html) if args.html else scrape_live(args.scope)
    write_outputs(rows)


if __name__ == "__main__":
    main()
