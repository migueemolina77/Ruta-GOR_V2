import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import re
import math
import os
from folium.features import DivIcon

st.set_page_config(page_title="Logística Rubiales v4.3", layout="wide")
st.title("🚜 Planificador de Ruta: Corrección de Origen")

# --- MOTOR DE GEORREFERENCIACIÓN RECALIBRADO (MAGNA-SIRGAS ORIGEN NACIONAL) ---
def proyectadas_a_latlon_colombia(este, norte):
    """
    Convierte coordenadas de Origen Nacional (CTM12) o Bogotá Este-Este 
    ajustando los parámetros para evitar el desplazamiento al océano.
    """
    try:
        # Parámetros GRS80 (Magna-SIRGAS)
        a = 6378137.0
        f = 1 / 298.257222101
        b = a * (1 - f)
        e2 = (a**2 - b**2) / a**2
        
        # --- CALIBRACIÓN DE ORIGEN ---
        # Si tus coordenadas están en el mar, el origen de longitud/latitud debe ajustarse.
        # Para Origen Nacional (CTM12): Lat 4.0, Lon -73.0
        lat0_deg = 4.0 
        lon0_deg = -73.0
        k0 = 0.9992 # Factor de escala Origen Nacional
        FE = 5000000.0 # Falso Este (Ajusta a 1.000.000 si es Este-Este antiguo)
        FN = 2000000.0 # Falso Norte
        
        # Detección automática de sistema (Si el Este es > 4 millones, es Origen Nacional)
        if este < 2000000:
            FE, FN = 1000000.0, 1000000.0
            lat0_deg, lon0_deg = 4.596200417, -74.077507917
            k0 = 1.0

        lat0 = math.radians(lat0_deg)
        lon0 = math.radians(lon0_deg)
        
        # Cálculos de proyección (Transversal de Mercator)
        n = (a - b) / (a + b)
        A = a / (1 + n) * (1 + (n**2)/4 + (n**4)/64)
        M = (norte - FN) / k0
        mu = M / (A * (1 - e2/4 - 3*e2**2/64))
        
        e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
        phi1 = mu + (3*e1/2 - 27*e1**3/32)*math.sin(2*mu) + (21*e1**2/16 - 55*e1**4/32)*math.sin(4*mu)
        
        N1 = a / math.sqrt(1 - e2 * math.sin(phi1)**2)
        R1 = a * (1 - e2) / (1 - e2 * math.sin(phi1)**2)**1.5
        D = (este - FE) / (N1 * k0)
        
        lat = phi1 - (N1 * math.tan(phi1) / R1) * (D**2/2 - (5 + 3*math.tan(phi1)**2)*D**4/24)
        lon = lon0 + (D - (1 + 2*math.tan(phi1)**2)*D**3/6) / math.cos(phi1)
        
        return math.degrees(lat), math.degrees(lon)
    except:
        return None, None

@st.cache_data
def cargar_datos_eco(file_source):
    try:
        if hasattr(file_source, 'name'):
            if file_source.name.endswith('.xlsx'): df = pd.read_excel(file_source)
            else: df = pd.read_csv(file_source, encoding='latin-1', sep=None, engine='python')
        else:
            df = pd.read_excel(file_source) if file_source.endswith('.xlsx') else pd.read_csv(file_source)
        
        df.columns = [re.sub(r'[^a-zA-Z]', '', str(c)).upper() for c in df.columns]
        c_name = next((c for c in df.columns if 'CLUSTER' in c or 'NAME' in c or 'PAD' in c), None)
        c_este = next((c for c in df.columns if 'ESTE' in c or 'COORDX' in c), None)
        c_norte = next((c for c in df.columns if 'NORTE' in c or 'COORDY' in c), None)
        
        df_f = df[[c_name, c_este, c_norte]].copy().dropna()
        df_f.columns = ['NAME', 'E', 'N']
        
        for c in ['E', 'N']:
            df_f[c] = pd.to_numeric(df_f[c].astype(str).str.replace(r'[^0-9.]', '', regex=True), errors='coerce')
        
        # Aplicamos la conversión recalibrada
        res = df_f.apply(lambda r: proyectadas_a_latlon_colombia(r['E'], r['N']), axis=1)
        df_f['lat'], df_f['lon'] = [r[0] for r in res], [r[1] for r in res]
        df_f['KEY'] = df_f['NAME'].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper()
        
        return df_f.dropna(subset=['lat']).groupby('NAME').first().reset_index()
    except:
        return pd.DataFrame()

# --- INTERFAZ ---
file = st.sidebar.file_uploader("Cargar Coordenadas (Excel/CSV):", type=["csv", "xlsx"])
df = cargar_datos_eco(file) if file else cargar_datos_eco("COORDENADAS_GOR.xlsx") if os.path.exists("COORDENADAS_GOR.xlsx") else pd.DataFrame()

puntos = []
if not df.empty:
    st.sidebar.success("📍 Sistema de Coordenadas Calibrado")
    busqueda = st.sidebar.text_area("Ruta de Trabajo (Escribe nombres):", "PAD 2")
    nombres_in = [n.strip().upper() for n in re.split(r'[\n,]+', busqueda) if n.strip()]
    for n in nombres_in:
        match = df[df['KEY'] == re.sub(r'[^a-zA-Z0-9]', '', n)]
        if not match.empty:
            puntos.append({'n': match.iloc[0]['NAME'], 'lat': match.iloc[0]['lat'], 'lon': match.iloc[0]['lon']})

# --- MAPA ---
centro = [puntos[0]['lat'], puntos[0]['lon']] if puntos else [3.991, -71.732]
m = folium.Map(location=centro, zoom_start=14)

folium.TileLayer(
    tiles='https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}',
    attr='Google Satellite',
    name='Google Satélite',
    overlay=False
).add_to(m)

for p in puntos:
    folium.Marker(
        [p['lat'], p['lon']],
        icon=DivIcon(icon_size=(150,20), icon_anchor=(0, 0),
        html=f'<div style="font-size: 12pt; color: yellow; font-weight: bold; background: rgba(0,0,0,0.5); padding: 2px;">{p["n"]}</div>')
    ).add_to(m)
    folium.CircleMarker([p['lat'], p['lon']], radius=5, color='red', fill=True).add_to(m)

st_folium(m, width=1000, height=500, key="mapa_v43")
