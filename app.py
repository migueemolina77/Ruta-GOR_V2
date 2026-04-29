import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import re
import math
import os
from folium.features import DivIcon

st.set_page_config(page_title="Logística Rubiales v3.8", layout="wide")
st.title("🚜 Sistema Logístico Rubiales v3.8 (Soporte Excel)")

def proyectadas_a_latlon_manual(este, norte):
    try:
        lat_0, lon_0 = 4.0, -73.0
        f_este, f_norte = 5000000.0, 2000000.0
        scale, r_earth = 0.9992, 6378137.0
        d_norte = (norte - f_norte) / scale
        d_este = (este - f_este) / scale
        lat = lat_0 + (d_norte / r_earth) * (180.0 / math.pi)
        lon = lon_0 + (d_este / (r_earth * math.cos(math.radians(lat_0)))) * (180.0 / math.pi)
        return lat, lon
    except: return None, None

@st.cache_data
def procesar_datos_universal(file_source, is_excel=False):
    try:
        # LEER SEGÚN EL TIPO DE ARCHIVO
        if is_excel or str(file_source).endswith('.xlsx'):
            df = pd.read_excel(file_source)
        else:
            df = pd.read_csv(file_source, encoding='latin-1', sep=None, engine='python')
        
        # Limpiar encabezados: Solo letras y en Mayúsculas
        df.columns = [re.sub(r'[^a-zA-Z]', '', str(c)).upper() for c in df.columns]
        
        # Buscar columnas clave (CLUSTER, ESTE, NORTE)
        col_c = next((c for c in df.columns if 'CLUSTER' in c), None)
        col_e = next((c for c in df.columns if 'ESTE' in c), None)
        col_n = next((c for c in df.columns if 'NORTE' in c), None)

        if not all([col_c, col_e, col_n]):
            st.error(f"⚠️ No encontré las columnas necesarias. El archivo tiene: {list(df.columns)}")
            return pd.DataFrame()

        df_f = df[[col_c, col_e, col_n]].copy()
        df_f.columns = ['NAME', 'E', 'N']
        
        # Limpiar números (quitar espacios o puntos de miles)
        for c in ['E', 'N']:
            df_f[c] = pd.to_numeric(df_f[c].astype(str).str.replace(r'[^0-9.]', '', regex=True), errors='coerce')
        
        df_f = df_f.dropna()

        # Conversión de coordenadas
        coords = df_f.apply(lambda r: proyectadas_a_latlon_manual(r['E'], r['N']), axis=1)
        df_f['lat'] = [c[0] for c in coords]
        df_f['lon'] = [c[1] for c in coords]
        df_f['KEY'] = df_f['NAME'].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper()
        
        return df_f.dropna(subset=['lat']).groupby('NAME').first().reset_index()
    except Exception as e:
        st.error(f"Error procesando el archivo: {e}")
        return pd.DataFrame()

# --- CARGA DE ARCHIVOS ---
st.sidebar.header("📂 Carga de Coordenadas")
file = st.sidebar.file_uploader("Sube tu Excel o CSV aquí:", type=["csv", "xlsx"])

df_maestro = pd.DataFrame()
if file:
    is_xlsx = file.name.endswith('.xlsx')
    df_maestro = procesar_datos_universal(file, is_excel=is_xlsx)
else:
    # Intento de carga automática del archivo en el repo
    for p in ["COORDENADAS_GOR.xlsx", "COORDENADAS_GOR.xlsx - data.csv"]:
        if os.path.exists(p):
            df_maestro = procesar_datos_universal(p, is_excel=p.endswith('.xlsx'))
            break

# --- MAPA ---
puntos = []
if not df_maestro.empty:
    st.sidebar.success(f"✅ {len(df_maestro)} Clústeres detectados")
    busqueda = st.sidebar.text_area("Ruta (Nombres de pozos):", "AGRIO-1")
    
    nombres_in = [n.strip().upper() for n in re.split(r'[\n,]+', busqueda) if n.strip()]
    for i, n in enumerate(nombres_in):
        k = re.sub(r'[^a-zA-Z0-9]', '', n)
        match = df_maestro[df_maestro['KEY'] == k]
        if not match.empty:
            puntos.append({'id': i+1, 'n': match.iloc[0]['NAME'], 'lat': match.iloc[0]['lat'], 'lon': match.iloc[0]['lon'], 'color': 'red'})

    if not puntos: # Si no hay búsqueda, mostrar algunos de prueba
        for i, row in df_maestro.head(5).iterrows():
            puntos.append({'id': '•', 'n': row['NAME'], 'lat': row['lat'], 'lon': row['lon'], 'color': 'blue'})

m = folium.Map(location=[3.99, -71.73], zoom_start=11)
for p in puntos:
    folium.Marker([p['lat'], p['lon']], tooltip=p['n'], icon=folium.Icon(color=p['color'])).add_to(m)
    folium.map.Marker([p['lat'], p['lon']], icon=DivIcon(icon_size=(20,20), icon_anchor=(-15,20),
        html=f'<div style="font-size: 9pt; color: white; background: {p["color"]}; border-radius: 4px; padding: 2px 5px; font-weight: bold; border: 1px solid white;">{p["n"]}</div>')).add_to(m)

st_folium(m, width=1100, height=600, key="mapa_v38")

if not df_maestro.empty:
    with st.expander("📖 Ver lista de clústeres en el archivo"):
        st.write(", ".join(df_maestro['NAME'].tolist()))
