import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import re
import requests
from folium.features import DivIcon

# Configuración de página
st.set_page_config(page_title="Logística Rubiales & CASE", layout="wide")

def dms_to_decimal(dms_str):
    try:
        if pd.isna(dms_str) or str(dms_str).strip() == "": return None
        if isinstance(dms_str, (int, float)): return float(dms_str)
        parts = re.findall(r"[-+]?\d*\.\d+|\d+", str(dms_str))
        if len(parts) == 1: return float(parts[0])
        if len(parts) < 3: return None
        deg, minu, sec = map(float, parts)
        decimal = deg + (minu / 60) + (sec / 3600)
        if any(char in str(dms_str).upper() for char in ['S', 'W', 'O']):
            decimal *= -1
        return decimal
    except:
        return None

def obtener_tramo_real(punto_a, punto_b):
    url = f"http://router.project-osrm.org/route/v1/driving/{punto_a['lon']},{punto_a['lat']};{punto_b['lon']},{punto_b['lat']}?overview=full&geometries=geojson"
    try:
        response = requests.get(url, timeout=5)
        data = response.json()
        if data['code'] == 'Ok':
            ruta = data['routes'][0]
            geometria = [[coord[1], coord[0]] for coord in ruta['geometry']['coordinates']]
            distancia_km = ruta['distance'] / 1000
            return geometria, distancia_km
    except:
        pass
    return [], 0

@st.cache_data
def cargar_base_coordenadas(file_path):
    # Cargamos el CSV completo para analizarlo
    df_raw = pd.read_csv(file_path, encoding='latin-1', header=None)
    
    # Buscamos la fila donde empieza la data (buscando "RB-1" o "RB-2")
    start_row = 0
    for i, row in df_raw.iterrows():
        if "RB-1" in str(row[0]):
            start_row = i
            break
            
    # Re-cargamos desde esa fila
    df = pd.read_csv(file_path, skiprows=start_row, encoding='latin-1', header=None)
    
    # Mapeo manual basado en tu archivo visual:
    # 0: Pozo, 2: Clúster, 5: Este, 6: Norte, 7: Latitud, 8: Longitud
    df_coords = df.iloc[:, [0, 2, 5, 6, 7, 8]].copy()
    df_coords.columns = ['pozo', 'cluster', 'este', 'norte', 'lat_raw', 'lon_raw']
    
    # Limpieza
    df_coords['lat_dec'] = df_coords['lat_raw'].apply(dms_to_decimal)
    df_coords['lon_dec'] = df_coords['lon_raw'].apply(dms_to_decimal)
    
    # Agrupación por clúster
    df_final = df_coords.dropna(subset=['lat_dec', 'lon_dec']).groupby('cluster').agg({
        'lat_dec': 'first', 
        'lon_dec': 'first', 
        'este': 'first',
        'norte': 'first',
        'pozo': lambda x: ', '.join(x.astype(str))
    }).reset_index()
    
    return df_final

# --- INTERFAZ ---
st.title("🚜 Plan de Movilización: Etapa 2")

try:
    df_maestro = cargar_base_coordenadas("COORDENADAS_RUB_CASE.csv")
    
    st.sidebar.header("Ruta de Equipos")
    ruta_input = st.sidebar.text_area("Clústeres en orden:", placeholder="RB-1\nCASE-01")
    nombres_ruta = [n.strip().upper() for n in re.split(r'[\n,]+', ruta_input) if n.strip()]

    puntos_ruta = []
    for i, nombre in enumerate(nombres_ruta):
        match = df_maestro[df_maestro['cluster'].astype(str).str.upper() == nombre]
        if not match.empty:
            puntos_ruta.append({
                'orden': i + 1,
                'nombre': nombre, 
                'lat': match.iloc[0]['lat_dec'], 
                'lon': match.iloc[0]['lon_dec'], 
                'pozos': match.iloc[0]['pozo'],
                'este': match.iloc[0]['este']
            })

    # Crear Mapa
    m = folium.Map(location=[df_maestro['lat_dec'].mean(), df_maestro['lon_dec'].mean()], zoom_start=11)

    if len(puntos_ruta) >= 2:
        total_km = 0
        resumen = []
        for i in range(len(puntos_ruta) - 1):
            p1, p2 = puntos_ruta[i], puntos_ruta[i+1]
            geometria, km = obtener_tramo_real(p1, p2)
            if geometria:
                folium.PolyLine(geometria, color='blue', weight=5).add_to(m)
                total_km += km
                resumen.append({"Tramo": f"{p1['nombre']} -> {p2['nombre']}", "KM": round(km, 2)})
        
        st.sidebar.table(resumen)
        st.sidebar.metric("Total Campaña", f"{total_km:.2f} Km")

    for p in puntos_ruta:
        folium.Marker([p['lat'], p['lon']], popup=f"Clúster: {p['nombre']}").add_to(m)
        folium.map.Marker([p['lat'], p['lon']], 
            icon=DivIcon(html=f'<div style="font-size: 12pt; font-weight: bold; color: white; background: black; border-radius: 50%; text-align: center; width: 25px;">{p["orden"]}</div>')).add_to(m)

    st_folium(m, width=1100, height=600)

except Exception as e:
    st.error(f"Error de lectura: {e}. Verifica que el archivo CSV no tenga filas vacías al inicio.")
