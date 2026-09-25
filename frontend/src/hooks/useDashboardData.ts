/**
 * NCPOR Dashboard Data Hooks
 * All frontend components use these hooks to fetch real data from the backend.
 */
import { useState, useEffect, useCallback } from 'react';

const BASE = '/api';

async function apiFetch(path: string) {
  const res = await fetch(`${BASE}/${path}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

async function apiPost(path: string, body: any) {
  const res = await fetch(`${BASE}/${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

// ── Generic fetch hook ───────────────────────────────────────────────────────
export function useApiData<T>(path: string, defaultValue: T, deps: any[] = []) {
  const [data, setData] = useState<T>(defaultValue);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await apiFetch(path);
      setData(result);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [path]);

  useEffect(() => { refetch(); }, [refetch, ...deps]);

  return { data, loading, error, refetch };
}

// ── Dashboard Overview ───────────────────────────────────────────────────────
export interface DashboardOverview {
  active_vessels: number;
  tracked_icebergs: number;
  new_icebergs_24h: number;
  high_risk_icebergs: number;
  sea_ice_concentration_pct: number;
  avg_wind_speed_kn: number;
  air_temperature_c: number;
  wave_height_m: number;
  active_alerts: number;
  timestamp: string;
  era5_source: string;
}

export function useDashboardOverview() {
  return useApiData<DashboardOverview | null>('dashboard/overview', null);
}

// ── Vessels ──────────────────────────────────────────────────────────────────
export interface Vessel {
  id: string;
  name: string;
  type: string;
  imo: string;
  mmsi: string;
  call_sign: string;
  length_m: number;
  beam_m: number;
  draft_m: number;
  ice_class: string;
  status: string;
  color: string;
  lat: number;
  lon: number;
  speed_kn: number;
  heading_deg: number;
  engine_load_pct: number;
  fuel_remaining_pct: number;
  next_waypoint: string;
  eta_next: string;
  distance_to_next_nm: number;
  origin?: string;
  destination?: string;
  weather_at_position?: WeatherData;
}

export function useVessels() {
  return useApiData<Vessel[]>('vessels', []);
}

// ── Weather ──────────────────────────────────────────────────────────────────
export interface WeatherData {
  wind_speed_kn: number;
  wind_dir_deg: number;
  temperature_c: number;
  pressure_hpa: number;
  sic: number;
  sic_pct: number;
  ice_thickness_m: number;
  wave_height_m: number;
  wave_period_s: number;
}

export function useWeather(lat: number, lon: number) {
  return useApiData<{ data: WeatherData; source: string } | null>(
    `weather?lat=${lat}&lon=${lon}`, null, [lat, lon]
  );
}

// ── Icebergs ─────────────────────────────────────────────────────────────────
export interface Iceberg {
  id: string;
  lat: number;
  lon: number;
  size_km: number;
  size_cat: string;
  drift_speed_kn: number;
  drift_dir_deg: number;
  risk: string;
  last_seen: string;
}

export function useIcebergs(risk?: string) {
  const path = risk ? `icebergs?risk=${risk}` : 'icebergs';
  return useApiData<Iceberg[]>(path, []);
}

export function useIcebergStats() {
  return useApiData<{ total: number; new_24h: number; high_risk: number; medium_risk: number; low_risk: number } | null>(
    'icebergs/stats', null
  );
}

// ── Routes ───────────────────────────────────────────────────────────────────
export interface RouteWaypoint {
  lat: number;
  lon: number;
  sic: number;
  wind_kn: number;
  wave_m: number;
}

export interface Route {
  type: string;
  routeKind?: 'eco' | 'fast' | 'safe';
  vesselId?: string;
  vesselName?: string;
  label: string;
  color: string;
  waypoints: RouteWaypoint[];
  distance_nm: number;
  eta_days: number;
  eta_hrs: number;
  fuel_mt: number;
  ice_risk: string;
  hull_stress: string;
  co2_mt: number;
}

export function useGenerateRoutes(startLat: number, startLon: number, endLat: number, endLon: number, trigger: boolean, triggerCount: number = 0) {
  const [routes, setRoutes] = useState<Route[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!trigger) { setRoutes([]); return; }
    setLoading(true);
    setError(null);
    apiPost('routes/generate', {
      start_lat: startLat, start_lon: startLon,
      end_lat: endLat, end_lon: endLon,
    }).then(res => {
      setRoutes(res.routes || []);
    }).catch(e => {
      setError(e.message);
    }).finally(() => setLoading(false));
  }, [trigger, startLat, startLon, endLat, endLon, triggerCount]);

  return { routes, loading, error };
}


export function useFleetRoutes(endLat: number, endLon: number, trigger: boolean) {
  const [routes, setRoutes] = useState<Route[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!trigger) return;
    setLoading(true);
    setError(null);
    apiPost('routes/fleet', {
      start_lat: 0, start_lon: 0,
      end_lat: endLat, end_lon: endLon,
    }).then(res => {
      setRoutes(res.routes || []);
    }).catch(e => {
      setError(e.message);
    }).finally(() => setLoading(false));
  }, [trigger, endLat, endLon]);

  return { routes, loading, error };
}

// ── SIC Forecast Grid ────────────────────────────────────────────────────────
export function useSicForecast(step: number) {
  return useApiData<any>(`forecast/sic?step=${step}`, null, [step]);
}

// ── Weather Forecast ─────────────────────────────────────────────────────────
export interface DayForecast {
  day: number;
  date: string;
  wind_speed_kn: number;
  temperature_c: number;
  wave_height_m: number;
  sic_pct: number;
  visibility: string;
}

export function useWeatherForecast(lat: number, lon: number) {
  return useApiData<{ forecasts: DayForecast[] } | null>(
    `forecast/weather?lat=${lat}&lon=${lon}`, null, [lat, lon]
  );
}

// ── Alerts ───────────────────────────────────────────────────────────────────
export interface Alert {
  id: string;
  time_utc: string;
  type: string;
  severity: string;
  message: string;
  vessel: string;
  location: string;
  status: string;
}

export function useAlerts() {
  return useApiData<Alert[]>('alerts', []);
}
