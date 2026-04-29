import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import re
import requests # Necesario para llamar al motor de rutas
from folium.features import DivIcon

st.set_page_config(page_title="Logística Rubiales v4.6", layout="wide")
st.title("🚜 Planificador Logístico: Rutas por Vía de Acceso")

# --- MOTOR DE RUTAS REALES (OSRM) ---
def obtener_ruta_vial(puntos):
    """Consulta la ruta real por carretera entre coordenadas"""
    if len(puntos) < 2: return None, 0
    
    # Formatear coordenadas para la API (lon,lat)
    coords_str = ";".join([f"{p['lon']},{p['lat']}" for p in puntos])
    url = f"http://router.project-osrm.org/route/v1/driving/{coords_str}?overview=full&geometries=geojson"
    
    try:
        r = requests.get(url)
        res = r.json()
        if res['code'] == 'Ok':
            geometria = res['routes'][0]['geometry']['coordinates']
            # OSRM devuelve [lon, lat], folium necesita [lat, lon]
            ruta_folium = [[lat, lon] for lon, lat in geometria]
            distancia_km = res['routes'][0]['distance'] / 1000
            return ruta_folium, distancia_km
    except:
        return None, 0
    return None, 0

# --- MOTOR DE COORDENADAS (Mismo que v4.5) ---
def proyectadas_a_latlon_colombia(este, norte):
    # (Mantenemos tu lógica de conversión Magna-SIRGAS / Origen Nacional aquí)
    # ... [Tu función de conversión actual] ...
    pass

# --- LÓGICA DE INTERFAZ ---
# [Carga de archivos y filtrado de clústeres similar a v4.5]
# Supongamos que ya tenemos la lista 'puntos_ruta' con las paradas

if len(puntos_ruta) >= 2:
    geometria_vial, km_reales = obtener_ruta_vial(puntos_ruta)
    
    col1, col2 = st.columns([3, 1])
    with col2:
        st.metric("Distancia por Vía", f"{km_reales:.2f} km")
        st.info("⚠️ El cálculo usa las vías registradas en OpenStreetMap.")

    # --- MAPA CON RUTA VIAL ---
    m = folium.Map(location=[puntos_ruta[0]['lat'], puntos_ruta[0]['lon']], zoom_start=13, tiles=None)
    folium.TileLayer(tiles='https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}', 
                     attr='Google Satellite Hybrid', name='Vista Logística').add_to(m)

    if geometria_vial:
        # Dibujamos la ruta que sigue las curvas de la carretera
        folium.PolyLine(geometria_vial, color="#00FFCC", weight=6, opacity=0.8, 
                        tooltip="Ruta de Acceso").add_to(m)

    # Añadir marcadores de Clústeres
    for p in puntos_ruta:
        folium.CircleMarker([p['lat'], p['lon']], radius=7, color='white', weight=2,
                            fill=True, fill_color='red', fill_opacity=1).add_to(m)
        folium.map.Marker([p['lat'], p['lon']], icon=DivIcon(icon_size=(150,20), 
            html=f'<div style="font-size: 10pt; color: white; font-weight: bold; background: rgba(0,0,0,0.6); padding: 2px 5px; border-radius: 3px;">{p["n"]}</div>')).add_to(m)

    st_folium(m, width=1100, height=550)
