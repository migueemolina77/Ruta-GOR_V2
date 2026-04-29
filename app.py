import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import re
import requests
from folium.features import DivIcon
from pyproj import Transformer
import os

# 1. Configuración de página
st.set_page_config(page_title="Logística Rubiales v2.2", layout="wide")

st.title("🚜 Diagnóstico y Plan Logístico v2.2")

# --- SECCIÓN DE DIAGNÓSTICO (Para saber qué pasa con el archivo) ---
st.subheader("🔍 Inspección del Entorno")
archivos_en_carpeta = os.listdir(".")
st.write("Archivos detectados en el servidor:", archivos_en_carpeta)

# Buscamos el archivo que más se parezca al CSV de coordenadas
archivo_objetivo = "COORDENADAS_GOR.xlsx - data.csv"

if archivo_objetivo in archivos_en_carpeta:
    st.success(f"✅ Archivo encontrado: {archivo_objetivo}")
else:
    st.error(f"❌ No se encuentra el archivo '{archivo_objetivo}'.")
    # Intentar buscar cualquier CSV por si el nombre cambió
    csv_alternativos = [f for f in archivos_en_carpeta if f.endswith('.csv')]
    if csv_alternativos:
        st.info(f"Se encontraron otros CSVs, intentaremos usar: {csv_alternativos[0]}")
        archivo_objetivo = csv_alternativos[0]

# --- FUNCIONES DE CARGA Y CONVERSIÓN ---

def proyectadas_a_latlon(este, norte):
    try:
        # Origen Nacional Colombia (EPSG:9377) -> WGS84 (EPSG:4326)
        transformer = Transformer.from_crs("EPSG:9377", "EPSG:4326", always_xy=True)
        lon, lat = transformer.transform(este, norte)
        return lat, lon
    except Exception as e:
        return None, None

@st.cache_data
def cargar_datos(path):
    try:
        # Intentar leer con encoding común en archivos de Excel/CSV colombianos
        df = pd.read_csv(path, encoding='latin-1', sep=None, engine='python')
        
        # Limpiar nombres de columnas (quitar espacios en blanco)
        df.columns = [c.strip().upper() for c in df.columns]
        
        st.write("Columnas detectadas en el CSV:", list(df.columns))
        
        # Seleccionar columnas necesarias
        # Según tu snippet: CLUSTER está en la col 1, POZO en 2, ESTE en 3, NORTE en 4
        required = ['CLUSTER', 'POZO', 'ESTE', 'NORTE']
        
        # Si no coinciden los nombres, usamos índices
        if all(col in df.columns for col in required):
            df_coords = df[required].copy()
        else:
            st.warning("Los nombres de columnas no coinciden, usando posición (1, 2, 3, 4)")
            df_coords = df.iloc[:, [1, 2, 3, 4]].copy()
            df_coords.columns = ['CLUSTER', 'POZO', 'ESTE', 'NORTE']
        
        # Convertir a número
        df_coords['ESTE'] = pd.to_numeric(df_coords['ESTE'], errors='coerce')
        df_coords['NORTE'] = pd.to_numeric(df_coords['NORTE'], errors='coerce')
        
        # Eliminar filas vacías
        df_coords = df_coords.dropna(subset=['ESTE', 'NORTE'])
        
        # Transformar coordenadas
        df_coords[['lat_dec', 'lon_dec']] = df_coords.apply(
            lambda row: proyectadas_a_latlon(row['ESTE'], row['NORTE']), 
            axis=1, result_type='expand'
        )
        
        # Agrupar por Clúster
        df_final = df_coords.dropna(subset=['lat_dec']).groupby('CLUSTER').agg({
            'lat_dec': 'first', 
            'lon_dec': 'first', 
            'ESTE': 'first',
            'NORTE': 'first',
            'POZO': lambda x: ', '.join(x.astype(str).unique())
        }).reset_index()
        
        return df_final
    except Exception as e:
        st.error(f"Error cargando el archivo: {e}")
        return None

# --- EJECUCIÓN PRINCIPAL ---

df_maestro = cargar_datos(archivo_objetivo)

if df_maestro is not None:
    st.success(f"Base de datos cargada con {len(df_maestro)} clústeres.")
    
    # Sidebar
    st.sidebar.header("Ruta de Movilización")
    input_text = st.sidebar.text_area("Lista de Clústeres (uno por línea):", placeholder="AGRIO-1\nCASE0015")
    nombres_busqueda = [n.strip().upper() for n in re.split(r'[\n,]+', input_text) if n.strip()]

    puntos_encontrados = []
    for i, nombre in enumerate(nombres_busqueda):
        # Filtro de búsqueda
        match = df_maestro[df_maestro['CLUSTER'].astype(str).str.upper() == nombre]
        
        if not match.empty:
            puntos_encontrados.append({
                'orden': i + 1,
                'nombre': nombre, 
                'lat': match.iloc[0]['lat_dec'], 
                'lon': match.iloc[0]['lon_dec'],
                'pozos': match.iloc[0]['POZO']
            })
        else:
            if nombre: st.sidebar.warning(f"No encontrado: {nombre}")

    # Visualización del Mapa
    if not df_maestro.empty:
        m = folium.Map(location=[df_maestro['lat_dec'].mean(), df_maestro['lon_dec'].mean()], zoom_start=11)
        
        # Dibujar líneas de ruta si hay más de 2 puntos
        if len(puntos_encontrados) >= 2:
            total_km = 0
            for j in range(len(puntos_encontrados) - 1):
                p1, p2 = puntos_encontrados[j], puntos_encontrados[j+1]
                url = f"http://router.project-osrm.org/route/v1/driving/{p1['lon']},{p1['lat']};{p2['lon']},{p2['lat']}?overview=full&geometries=geojson"
                try:
                    res = requests.get(url, timeout=5).json()
                    if res['code'] == 'Ok':
                        geom = [[c[1], c[0]] for c in res['routes'][0]['geometry']['coordinates']]
                        total_km += res['routes'][0]['distance'] / 1000
                        folium.PolyLine(geom, color="red", weight=4).add_to(m)
                except: pass
            st.sidebar.metric("Distancia Total Estimada", f"{total_km:.2f} Km")

        # Marcadores
        for p in puntos_encontrados:
            folium.Marker(
                [p['lat'], p['lon']],
                popup=f"Clúster: {p['nombre']}\nPozos: {p['pozos']}",
                icon=folium.Icon(color='red', icon='location-dot', prefix='fa')
            ).add_to(m)
            
            folium.map.Marker(
                [p['lat'], p['lon']],
                icon=DivIcon(icon_size=(20,20), icon_anchor=(10,10),
                html=f'<div style="font-size: 10pt; color: white; background: red; border-radius: 50%; width: 20px; height: 20px; text-align: center; font-weight: bold; border: 1px solid white;">{p["orden"]}</div>')
            ).add_to(m)

        st_folium(m, width=1100, height=600)

else:
    st.warning("⚠️ La base de datos no se pudo generar. Revisa el diagnóstico arriba.")
