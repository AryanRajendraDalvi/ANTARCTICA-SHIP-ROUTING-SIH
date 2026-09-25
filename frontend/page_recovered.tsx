"use client";
import React, { useState, useEffect, useRef, useCallback } from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { twMerge } from 'tailwind-merge';
import clsx from 'clsx';
import {
  Navigation, Map as MapIcon, Thermometer, Ship, BarChart2, Bell, FileText, Search, User,
  Crosshair, Layers, Settings, AlertTriangle, Info, Wind, Droplets, Activity, Clock,
  CheckCircle2, ChevronDown, MonitorSmartphone, MessageSquare, BookOpen, Eye,
  RefreshCw, Download, Plus, Edit, Trash2, Filter, Loader2, LoaderCircle
} from 'lucide-react';

const ROUTE_DESTINATIONS = [
  { id: 'maitri', label: 'Maitri Station, Antarctica', lat: -70.766, lon: 11.833 },
  { id: 'bharati', label: 'Bharati Station, Antarctica', lat: -69.400, lon: 76.183 },
  { id: 'davis', label: 'Davis Station, Antarctica', lat: -68.577, lon: 77.967 },
  { id: 'casey', label: 'Casey Station, Antarctica', lat: -66.282, lon: 110.527 },
  { id: 'mcmurdo', label: 'McMurdo Station, Antarctica', lat: -77.842, lon: 166.686 },
  { id: 'rothera', label: 'Rothera Station, Antarctica', lat: -67.568, lon: -68.128 },
  { id: 'mawson', label: 'Mawson Station, Antarctica', lat: -67.603, lon: 62.876 },
  { id: 'zhongshan', label: 'Zhongshan Station, Antarctica', lat: -69.373, lon: 76.377 },
  { id: 'dumont-durville', label: 'Dumont d\'Urville Station, Antarctica', lat: -66.663, lon: 140.002 },
  { id: 'neumayer', label: 'Neumayer Station III, Antarctica', lat: -70.673, lon: -8.274 },
  { id: 'princess-elisabeth', label: 'Princess Elisabeth Station, Antarctica', lat: -71.950, lon: 23.347 },
  { id: 'troll', label: 'Troll Station, Antarctica', lat: -72.011, lon: 2.534 },
  { id: 'sanae', label: 'SANAE IV Station, Antarctica', lat: -71.673, lon: -2.842 },
  { id: 'cape-town', label: 'Cape Town, South Africa', lat: -33.925, lon: 18.423 },
  { id: 'port-louis', label: 'Port Louis, Mauritius', lat: -20.160, lon: 57.501 },
];

function getDestCoords(destName) {
  const destination = ROUTE_DESTINATIONS.find(item => item.label === destName)
    || ROUTE_DESTINATIONS.find(item => destName?.includes(item.label.split(',')[0] || ''))
    || ROUTE_DESTINATIONS[0];
  return [destination.lat, destination.lon];
}

function cn(...inputs) {
  return (0, twMerge)((0, clsx)(inputs));
}
function SharedMap({
  zoom = 3.5,
  center = [68.0, -66.0]
}) {
  const ref = (0, useRef)(null);
  const inst = (0, useRef)(null);
  (0, useEffect)({
    "SharedMap.useEffect": () => {
      if (inst.current || !ref.current) return;
      const map = new Map({
        container: ref.current,
        style: {
          version: 8,
          sources: {
            sat: {
              type: 'raster',
              tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
              tileSize: 256
            }
          },
          layers: [{
            id: 'sat',
            type: 'raster',
            source: 'sat'
          }]
        },
        center,
        zoom
      });
      inst.current = map;
      map.addControl(new NavigationControl({
        showCompass: false
      }), 'bottom-right');
      map.on('load', {
        "SharedMap.useEffect": () => {
          const feats = [];
          for (let lo = 20; lo <= 100; lo += 2) for (let la = -75; la <= -60; la += 2) feats.push({
            type: 'Feature',
            geometry: {
              type: 'Point',
              coordinates: [lo, la]
            },
            properties: {
              sic: Math.max(0, Math.min(1, (la + 60) / -15 + (Math.random() * 0.4 - 0.2)))
            }
          });
          map.addSource('sic', {
            type: 'geojson',
            data: {
              type: 'FeatureCollection',
              features: feats
            }
          });
          map.addLayer({
            id: 'sic-heat',
            type: 'heatmap',
            source: 'sic',
            paint: {
              'heatmap-weight': ['get', 'sic'],
              'heatmap-intensity': 1,
              'heatmap-color': ['interpolate', ['linear'], ['heatmap-density'], 0, 'rgba(255,255,255,0)', 0.4, '#60a5fa', 0.7, '#fde047', 1, '#dc2626'],
              'heatmap-radius': 40,
              'heatmap-opacity': 0.7
            }
          });
          const mk = {
            "SharedMap.useEffect.mk": (color, bg = false) => {
              const el = document.createElement('div');
              el.className = bg ? 'w-4 h-4 bg-white/80 border-2 border-slate-300 rounded shadow-sm' : `w-3 h-3 ${color} rounded-full border-2 border-white shadow-md`;
              return el;
            }
          }["SharedMap.useEffect.mk"];
          new Marker({
            element: mk('bg-green-500')
          }).setLngLat([72.341, -66.247]).addTo(map);
          new Marker({
            element: mk('bg-blue-500')
          }).setLngLat([64.998, -68.112]).addTo(map);
          new Marker({
            element: mk('bg-slate-400')
          }).setLngLat([55.221, -62.441]).addTo(map);
          new Marker({
            element: mk('', true)
          }).setLngLat([71.5, -65.8]).addTo(map);
          new Marker({
            element: mk('', true)
          }).setLngLat([68.5, -67.2]).addTo(map);
          map.addSource('eco', {
            type: 'geojson',
            data: {
              type: 'Feature',
              properties: {},
              geometry: {
                type: 'LineString',
                coordinates: [[72.341, -66.247], [71.0, -65.5], [69.0, -66.0], [66.0, -66.5]]
              }
            }
          });
          map.addLayer({
            id: 'eco-line',
            type: 'line',
            source: 'eco',
            layout: {
              'line-cap': 'round',
              'line-join': 'round'
            },
            paint: {
              'line-color': '#22c55e',
              'line-width': 2,
              'line-dasharray': [2, 2]
            }
          });
          map.addSource('safe', {
            type: 'geojson',
            data: {
              type: 'Feature',
              properties: {},
              geometry: {
                type: 'LineString',
                coordinates: [[72.341, -66.247], [72.0, -64.0], [69.0, -64.0], [66.0, -66.5]]
              }
            }
          });
          map.addLayer({
            id: 'safe-line',
            type: 'line',
            source: 'safe',
            layout: {
              'line-cap': 'round',
              'line-join': 'round'
            },
            paint: {
              'line-color': '#3b82f6',
              'line-width': 2,
              'line-dasharray': [4, 2]
            }
          });
        }
      }["SharedMap.useEffect"]);
      return {
        "SharedMap.useEffect": () => {
          map.remove();
          inst.current = null;
        }
      }["SharedMap.useEffect"];
    }
  }["SharedMap.useEffect"], []);
  return <div ref={ref} className="absolute inset-0 w-full h-full bg-slate-800"></div>;
}
function OnshoreOverview() {
  return <div className="flex flex-col h-full p-3 gap-3 bg-slate-100">{<div className="grid grid-cols-4 gap-3 shrink-0">{[{
        icon: <Ship size={20} className="text-blue-500"></Ship>,
        val: '3',
        label: 'Active Vessels',
        bg: 'bg-blue-50'
      }, {
        icon: <Map size={20} className="text-slate-500"></Map>,
        val: '248',
        label: 'Tracked Icebergs',
        bg: 'bg-slate-50'
      }, {
        icon: <Layers size={20} className="text-indigo-500"></Layers>,
        val: '42%',
        sub: 'Sea Ice Concentration',
        bg: 'bg-indigo-50'
      }, {
        icon: <AlertTriangle size={20} className="text-red-500"></AlertTriangle>,
        val: '2',
        label: 'Active Alerts',
        bg: 'bg-red-50'
      }].map((k, i) => <div className="bg-white rounded-lg shadow-sm border border-slate-200 flex items-center p-3 gap-3">{<div className={cn('w-10 h-10 rounded-lg flex items-center justify-center shrink-0', k.bg)}>{k.icon}</div>}{<div>{<div className="text-xl font-black text-slate-800">{k.val}</div>}{<div className="text-[10px] text-slate-500">{k.label || k.sub}</div>}</div>}</div>)}</div>}{<div className="flex flex-1 gap-3 min-h-0">{<div className="flex-[2] relative rounded-lg overflow-hidden border border-slate-300 shadow-sm">{<SharedMap></SharedMap>}{<div className="absolute top-3 left-3 z-10 bg-white/95 rounded-md px-3 py-1.5 text-xs font-bold border border-slate-200 shadow flex items-center gap-2 cursor-pointer">Southern Ocean {<ChevronDown size={12}></ChevronDown>}</div>}{<div className="absolute top-3 right-3 z-10 bg-white/95 rounded-lg p-3 border border-slate-200 shadow text-[10px] space-y-1.5 w-36">{['Vessels', 'Icebergs', 'Sea Ice (SIC)'].map(l => <label className="flex items-center gap-1.5 cursor-pointer">{<input type="checkbox" defaultChecked={true} className="rounded accent-blue-500"></input>}{<span>{l}</span>}</label>)}{<div className="h-px bg-slate-200 my-1"></div>}{<div className="flex items-center gap-1.5">{<div className="w-4 h-px bg-green-500 border-dashed border-b-2"></div>}{<span>Planned Route</span>}</div>}{<div className="flex items-center gap-1.5">{<div className="w-4 h-px bg-blue-500 border-dashed border-b-2"></div>}{<span>Alt Route</span>}</div>}{<div className="flex items-center gap-1.5">{<div className="w-3 h-3 border border-red-400 bg-red-100 rounded-sm"></div>}{<span>Risk Area</span>}</div>}{<div className="flex items-center gap-1.5">{<div className="w-4 h-px bg-slate-600 border-dashed border-b-2"></div>}{<span>Iceberg Drift</span>}</div>}</div>}{<div className="absolute top-1/3 left-1/2 -translate-x-1/2 bg-[#1e293b]/90 text-white text-[10px] p-2 rounded shadow-lg border border-slate-600 pointer-events-none">{<div className="font-bold text-xs mb-1">Iceberg ID: A-7421</div>}{<div>Drift Speed: 0.8 kn</div>}{<div>Direction: 120°</div>}{<div>Size: Large (1.2 km)</div>}{<div className="text-slate-400 mt-1">Last Update: 2 hrs ago</div>}</div>}</div>}{<div className="flex-1 bg-white rounded-lg border border-slate-200 shadow-sm flex flex-col overflow-hidden">{<div className="p-3 border-b border-slate-100 text-xs font-bold text-slate-800">Recent Activity</div>}{<div className="p-4 space-y-5 overflow-y-auto flex-1">{[{
            color: 'bg-green-500',
            title: 'RV Bharati',
            msg: 'Entered high ice area',
            time: '09:11 UTC'
          }, {
            color: 'bg-blue-500',
            title: 'New iceberg detected',
            msg: 'Size: Large (1.2 km)',
            time: '08:32 UTC'
          }, {
            color: 'bg-blue-500',
            title: 'SA Agulhas II',
            msg: 'Route monitoring update',
            time: '08:15 UTC'
          }, {
            color: 'bg-slate-400',
            title: 'Weather update',
            msg: 'Strong winds (45 kn) expected at 07:50 UTC',
            time: '07:50 UTC'
          }].map((a, i) => <div className="relative pl-4 border-l-2" style={{
            borderColor: a.color.replace('bg-', '#')
          }}>{<div className={cn('absolute -left-1.5 top-0 w-2.5 h-2.5 rounded-full', a.color)}></div>}{<div className="text-xs font-bold text-slate-800">{a.title}</div>}{<div className="text-[10px] text-slate-500">{a.msg}</div>}{<div className="text-[9px] text-slate-400 mt-0.5">{a.time}</div>}</div>)}</div>}</div>}</div>}</div>;
}
function OnshoreVessels() {
  const [selected, setSelected] = (0, useState)(0);
  const vessels = [{
    name: 'RV Bharati',
    type: 'Research Vessel',
    color: 'bg-green-500',
    lat: '-66.247°',
    lon: '72.341°',
    speed: '12.4 kn',
    hdg: '087°'
  }, {
    name: 'SA Agulhas II',
    type: 'Icebreaker',
    color: 'bg-blue-600',
    lat: '-68.112°',
    lon: '64.998°',
    speed: '11.2 kn',
    hdg: '103°'
  }, {
    name: 'MV S.A. Explorer',
    type: 'Support Vessel',
    color: 'bg-slate-400',
    lat: '-62.441°',
    lon: '55.221°',
    speed: '10.1 kn',
    hdg: '076°'
  }];
  return <div className="flex h-full p-3 gap-3 bg-slate-100">{<div className="w-72 bg-white rounded-lg border border-slate-200 shadow-sm flex flex-col shrink-0">{<div className="p-3 border-b border-slate-100 flex items-center justify-between">{<span className="text-xs font-bold text-slate-800">Vessels (3)</span>}</div>}{<div className="p-2 border-b border-slate-100">{<div className="relative">{<Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-slate-400"></Search>}{<input className="w-full text-[11px] pl-7 pr-2 py-1.5 bg-slate-50 border border-slate-200 rounded" placeholder="Search vessel..."></input>}</div>}</div>}{<div className="flex-1 overflow-y-auto">{vessels.map((v, i) => <div onClick={() => setSelected(i)} className={cn('p-3 border-b border-slate-100 cursor-pointer flex items-center gap-3 hover:bg-slate-50', selected === i && 'bg-blue-50 border-l-4 border-blue-500')}>{<div className="w-14 h-12 bg-slate-200 rounded shrink-0 overflow-hidden flex items-center justify-center">{<Ship size={20} className="text-slate-400"></Ship>}</div>}{<div className="min-w-0">{<div className="flex items-center gap-1">{<div className={cn('w-1.5 h-1.5 rounded-full shrink-0', v.color)}></div>}{<span className="text-xs font-bold text-slate-800 truncate">{v.name}</span>}</div>}{<div className="text-[9px] text-slate-500">{v.type}</div>}{<div className="text-[9px] text-slate-600 mt-0.5">Lat: {v.lat} Lon: {v.lon}</div>}{<div className="text-[9px] text-slate-600">Speed: {v.speed} Heading: {v.hdg}</div>}</div>}</div>)}</div>}</div>}{<div className="flex-1 relative rounded-lg overflow-hidden border border-slate-300 shadow-sm">{<SharedMap></SharedMap>}{<div className="absolute top-3 right-3 z-10 bg-white/95 rounded-lg p-3 border border-slate-200 shadow text-[10px] space-y-1.5 w-40">{<div className="font-bold text-slate-700 mb-2">Legend</div>}{<div className="flex items-center gap-2">{<div className="w-4 h-px bg-green-500 border-dashed border-b-2"></div>}{<span>Planned Route (Fast)</span>}</div>}{<div className="flex items-center gap-2">{<div className="w-4 h-px bg-blue-500 border-dashed border-b-2"></div>}{<span>Alternative Route</span>}</div>}{<div className="flex items-center gap-2">{<div className="w-3 h-3 border border-blue-500 rounded-full"></div>}{<span>Fast Track</span>}</div>}</div>}</div>}</div>;
}
function OnshoreIceWeather() {
  const [tab, setTab] = (0, useState)('Sea Ice');
  const tabs = ['Sea Ice', 'Weather', 'Ocean Currents', 'Waves'];
  return <div className="flex h-full p-3 gap-3 bg-slate-100">{<div className="flex-[2] flex flex-col gap-3">{<div className="flex items-center gap-2">{tabs.map(t => <button onClick={() => setTab(t)} className={cn('px-4 py-1.5 text-xs font-bold rounded-md transition-colors', tab === t ? 'bg-blue-600 text-white' : 'bg-white text-slate-600 border border-slate-200 hover:bg-slate-50')}>{t}</button>)}{<div className="ml-auto text-[10px] text-slate-400 font-medium">12 Sep 2026, 10:45 UTC</div>}</div>}{<div className="flex-1 relative rounded-lg overflow-hidden border border-slate-300 shadow-sm">{<SharedMap></SharedMap>}{<div className="absolute top-3 left-3 z-10 bg-[#1e293b]/90 text-white text-[10px] p-2 rounded shadow font-bold">Sea Ice Concentration</div>}{<div className="absolute top-3 right-3 z-10 bg-white/95 rounded p-2 border border-slate-200 shadow text-[9px] space-y-1 w-28">{<div className="font-bold text-slate-700 mb-1">Concentration (%)</div>}{[['0–20', 'bg-blue-200'], ['20–40', 'bg-blue-400'], ['40–60', 'bg-blue-600'], ['60–80', 'bg-yellow-500'], ['80–100', 'bg-red-600']].map(([label, color]) => <div className="flex items-center gap-2">{<div className={cn('w-3 h-2 rounded-sm', color)}></div>}{<span className="text-slate-600">{label}</span>}</div>)}</div>}</div>}{<div className="h-16 grid grid-cols-4 gap-3 shrink-0">{[{
          icon: <Layers size={18} className="text-blue-500"></Layers>,
          label: 'Ice Thickness',
          val: '0.8 m'
        }, {
          icon: <Thermometer size={18} className="text-cyan-500"></Thermometer>,
          label: 'Air Temperature',
          val: '-11 °C'
        }, {
          icon: <Wind size={18} className="text-sky-500"></Wind>,
          label: 'Wind Speed',
          val: '22 kn (SW)'
        }, {
          icon: <Activity size={18} className="text-indigo-500"></Activity>,
          label: 'Wave Height',
          val: '1.4 m'
        }].map((k, i) => <div className="bg-white rounded-lg border border-slate-200 shadow-sm flex items-center p-2 gap-2">{k.icon}{<div>{<div className="text-[9px] text-slate-500">{k.label}</div>}{<div className="text-sm font-bold text-slate-800">{k.val}</div>}</div>}</div>)}</div>}</div>}</div>;
}
function OnshoreRoute() {
  return <div className="flex flex-col h-full p-3 gap-3 bg-slate-100">{<div className="flex items-center gap-2">{['Plan New Route', 'Compare Routes', 'Route Library'].map((t, i) => <button className={cn('px-4 py-1.5 text-xs font-bold rounded-md', i === 0 ? 'bg-blue-600 text-white' : 'bg-white text-slate-600 border border-slate-200 hover:bg-slate-50')}>{t}</button>)}</div>}{<div className="flex flex-1 gap-3 min-h-0">{<div className="w-64 bg-white rounded-lg border border-slate-200 shadow-sm p-4 shrink-0 overflow-y-auto space-y-4">{[['Select Vessel', 'RV Bharati'], ['Departure Port', 'Cape Town'], ['Destination', 'Maitri Station']].map(([l, v]) => <div>{<label className="text-[10px] font-bold text-slate-700 block mb-1">{l}</label>}{<select className="w-full text-xs border border-slate-300 rounded p-1.5 bg-slate-50 outline-none">{<option>{v}</option>}</select>}</div>)}{<div className="border-t border-slate-100 pt-3">{<div className="text-[10px] font-bold text-slate-700 mb-2">Optimization Priority</div>}{<div className="space-y-2">{['Lowest Fuel Consumption', 'Safest Route', 'Fastest Route', 'Avoid High Ice Areas'].map((o, i) => <label className="flex items-center gap-2 text-xs text-slate-600 cursor-pointer">{<input type="checkbox" defaultChecked={i !== 2} className="rounded accent-blue-500"></input>}{<span>{o}</span>}</label>)}</div>}</div>}{<button className="w-full bg-blue-600 text-white text-xs font-bold py-2 rounded shadow hover:bg-blue-700 transition-colors">Generate Routes</button>}</div>}{<div className="flex-1 relative rounded-lg overflow-hidden border border-slate-300 shadow-sm">{<SharedMap></SharedMap>}{<div className="absolute top-3 right-3 z-10 bg-white/95 rounded-lg p-2.5 border border-slate-200 shadow text-[10px] space-y-1.5 w-36">{<div className="flex items-center gap-2">{<div className="w-4 h-px bg-green-500 border-dashed border-b-2"></div>}{<span>Eco Route</span>}</div>}{<div className="flex items-center gap-2">{<div className="w-4 h-px bg-blue-500 border-dashed border-b-2"></div>}{<span>Safe Route</span>}</div>}{<div className="flex items-center gap-2">{<div className="w-4 h-px bg-red-500 border-dashed border-b-2"></div>}{<span>Fastest Route</span>}</div>}</div>}{<div className="absolute bottom-12 right-16 z-10 bg-white/90 border border-blue-300 text-[10px] font-bold text-blue-700 px-2 py-1 rounded shadow">Cape Town</div>}{<div className="absolute bottom-8 left-1/2 z-10 bg-white/90 border border-green-300 text-[10px] font-bold text-green-700 px-2 py-1 rounded shadow">Maitri Station</div>}</div>}</div>}</div>;
}
function OnshoreIceberg() {
  return <div className="flex h-full p-3 gap-3 bg-slate-100">{<div className="flex-[2] relative rounded-lg overflow-hidden border border-slate-300 shadow-sm">{<SharedMap></SharedMap>}{<div className="absolute top-1/3 left-1/2 -translate-x-1/2 z-10 bg-[#1e293b]/90 text-white text-[10px] p-3 rounded shadow-lg border border-slate-600 w-48 pointer-events-none">{<div className="font-bold text-xs mb-2">Iceberg ID: A-7421</div>}{<div>Size: Large (1.2 km)</div>}{<div>Lat: -68.771°</div>}{<div>Lon: -70.112°</div>}{<div>Drift Speed: 0.8 kn</div>}{<div>Direction: 120°</div>}{<div className="text-slate-400 mt-1">Last Update: 2 hrs ago</div>}</div>}{<div className="absolute top-3 right-3 z-10 bg-white/95 rounded-lg p-3 border border-slate-200 shadow text-[10px] space-y-1.5 w-40">{<div className="font-bold text-slate-700 mb-1">Iceberg Size</div>}{[['All Icebergs', 'bg-slate-400'], ['Large (>1 km)', 'bg-red-500'], ['Medium (300m–1km)', 'bg-orange-400'], ['Small (<300m)', 'bg-yellow-400']].map(([l, c]) => <div className="flex items-center gap-2">{<div className={cn('w-3 h-3 rounded-sm', c)}></div>}{<span>{l}</span>}</div>)}</div>}</div>}{<div className="w-64 bg-white rounded-lg border border-slate-200 shadow-sm p-4 space-y-4 shrink-0">{<div className="flex items-center gap-3">{<div className="bg-slate-100 rounded-lg p-3 flex-1 text-center">{<div className="text-2xl font-black text-slate-800">248</div>}{<div className="text-[9px] text-slate-500">Tracked Icebergs</div>}</div>}{<div className="bg-red-50 rounded-lg p-3 flex-1 text-center border border-red-200">{<div className="text-2xl font-black text-red-600">12</div>}{<div className="text-[9px] text-red-500">New (Last 24h)</div>}</div>}</div>}{<div className="bg-orange-50 rounded-lg p-3 border border-orange-200">{<div className="text-[9px] font-bold text-orange-700 mb-1">HIGH RISK (Near Routes)</div>}{<div className="text-2xl font-black text-orange-600">5</div>}</div>}{<div className="border-t border-slate-100 pt-3 space-y-2">{[{
          id: 'A-7421',
          size: 'Large',
          risk: 'High',
          riskColor: 'bg-red-500'
        }, {
          id: 'B-3312',
          size: 'Medium',
          risk: 'Medium',
          riskColor: 'bg-orange-400'
        }, {
          id: 'C-0091',
          size: 'Small',
          risk: 'Low',
          riskColor: 'bg-green-500'
        }].map(b => <div className="flex items-center justify-between text-[10px] bg-slate-50 rounded p-2">{<span className="font-bold text-slate-700">{b.id}</span>}{<span className="text-slate-500">{b.size}</span>}{<span className={cn('text-white px-2 py-0.5 rounded-full text-[9px] font-bold', b.riskColor)}>{b.risk}</span>}</div>)}</div>}</div>}</div>;
}
function OnshoreAlerts() {
  const [filter, setFilter] = (0, useState)('All Alerts');
  const filters = ['All Alerts (3)', 'Vessel Alerts (2)', 'Ice Alerts (1)', 'Weather Alerts', 'System'];
  const alerts = [{
    time: '10:32',
    type: 'Iceberg',
    sev: 'High',
    sevColor: 'bg-red-500',
    msg: 'Potential iceberg intersection in 24 hours',
    vessel: 'RV Bharati',
    status: 'Open',
    statusColor: 'bg-red-100 text-red-700'
  }, {
    time: '08:14',
    type: 'Sea Ice',
    sev: 'Medium',
    sevColor: 'bg-orange-400',
    msg: 'High ice concentration ahead (>85% SIC)',
    vessel: 'SA Agulhas II',
    status: 'Acknowledged',
    statusColor: 'bg-amber-100 text-amber-700'
  }, {
    time: '06:03',
    type: 'Weather',
    sev: 'Low',
    sevColor: 'bg-blue-500',
    msg: 'Strong winds (45 kn) expected in your area',
    vessel: 'M.V.S.A. Explorer',
    status: 'Open',
    statusColor: 'bg-red-100 text-red-700'
  }];
  return <div className="flex flex-col h-full p-3 gap-3 bg-slate-100">{<div className="flex items-center gap-2 flex-wrap">{filters.map(f => <button onClick={() => setFilter(f)} className={cn('px-3 py-1.5 text-[10px] font-bold rounded-md transition-colors', filter === f ? 'bg-blue-600 text-white' : 'bg-white text-slate-600 border border-slate-200 hover:bg-slate-50')}>{f}</button>)}{<div className="ml-auto flex items-center gap-2 text-[10px] text-slate-500">{<Filter size={12}></Filter>}Filter: All</div>}</div>}{<div className="bg-white rounded-lg border border-slate-200 shadow-sm overflow-hidden flex-1">{<table className="w-full text-[10px]">{<thead>{<tr className="bg-slate-50 border-b border-slate-200">{['Time (UTC)', 'Type', 'Severity', 'Message', 'Vessel / Location', 'Status', 'Action'].map(h => <th className="text-left px-3 py-2 font-bold text-slate-600 text-[10px]">{h}</th>)}</tr>}</thead>}{<tbody>{alerts.map((a, i) => <tr className="border-b border-slate-100 hover:bg-slate-50">{<td className="px-3 py-3 text-slate-500 font-medium">{a.time}</td>}{<td className="px-3 py-3 flex items-center gap-1.5 mt-1">{<AlertTriangle size={12} className="text-orange-500"></AlertTriangle>}{<span className="font-medium text-slate-700">{a.type}</span>}</td>}{<td className="px-3 py-3">{<span className={cn('text-white px-2 py-0.5 rounded-full font-bold text-[9px]', a.sevColor)}>{a.sev}</span>}</td>}{<td className="px-3 py-3 text-slate-600 max-w-xs">{a.msg}</td>}{<td className="px-3 py-3 font-medium text-slate-700">{a.vessel}</td>}{<td className="px-3 py-3">{<span className={cn('px-2 py-0.5 rounded-full text-[9px] font-bold', a.statusColor)}>{a.status}</span>}</td>}{<td className="px-3 py-3">{<button className="text-blue-600 hover:underline text-[10px] font-bold">View</button>}</td>}</tr>)}</tbody>}</table>}</div>}</div>;
}
function OnshoreData() {
  const [tab, setTab] = (0, useState)('Sea Ice Forecast');
  const tabs = ['Sea Ice Forecast', 'Weather Forecast', 'Ocean Currents', 'Download Data'];
  return <div className="flex h-full p-3 gap-3 bg-slate-100">{<div className="w-56 bg-white rounded-lg border border-slate-200 shadow-sm p-4 space-y-4 shrink-0">{<div>{<label className="text-[10px] font-bold text-slate-700 block mb-1">Region</label>}{<select className="w-full text-xs border border-slate-300 rounded p-1.5 bg-slate-50 outline-none">{<option>Southern Ocean</option>}</select>}</div>}{<div>{<label className="text-[10px] font-bold text-slate-700 block mb-1">Parameter</label>}{<select className="w-full text-xs border border-slate-300 rounded p-1.5 bg-slate-50 outline-none">{<option>Sea Ice Concentration</option>}</select>}</div>}{<div>{<label className="text-[10px] font-bold text-slate-700 block mb-1">Forecast Horizon</label>}{<select className="w-full text-xs border border-slate-300 rounded p-1.5 bg-slate-50 outline-none">{<option>7 days</option>}</select>}</div>}{<button className="w-full bg-blue-600 text-white text-xs font-bold py-2 rounded hover:bg-blue-700">View Forecast</button>}</div>}{<div className="flex-1 flex flex-col gap-3">{<div className="flex gap-2">{tabs.map(t => <button onClick={() => setTab(t)} className={cn('px-3 py-1.5 text-[10px] font-bold rounded-md', tab === t ? 'bg-blue-600 text-white' : 'bg-white text-slate-600 border border-slate-200 hover:bg-slate-50')}>{t}</button>)}</div>}{<div className="flex flex-1 gap-3">{['Day 1\n12 Sep', 'Day 3\n14 Sep', 'Day 5\n16 Sep', 'Day 7\n18 Sep'].map((d, i) => <div className="flex-1 bg-white rounded-lg border border-slate-200 shadow-sm overflow-hidden">{<div className="bg-slate-50 border-b border-slate-200 px-3 py-2 text-[10px] font-bold text-slate-700 whitespace-pre-line">{d}</div>}{<div className="relative h-full">{<div className="absolute inset-0 bg-gradient-to-b from-blue-400/30 via-yellow-400/20 to-red-500/40"></div>}</div>}</div>)}</div>}</div>}</div>;
}
function OnshoreReports() {
  const [tab, setTab] = (0, useState)('Vessel Reports');
  return <div className="flex h-full p-3 gap-3 bg-slate-100">{<div className="flex-1 flex flex-col gap-3">{<div className="flex gap-2">{['Vessel Reports', 'Environmental Reports', 'Compliance Reports'].map(t => <button onClick={() => setTab(t)} className={cn('px-4 py-1.5 text-[10px] font-bold rounded-md', tab === t ? 'bg-blue-600 text-white' : 'bg-white text-slate-600 border border-slate-200 hover:bg-slate-50')}>{t}</button>)}</div>}{<div className="bg-white rounded-lg border border-slate-200 shadow-sm p-4 space-y-4 flex-1">{<div>{<label className="text-[10px] font-bold text-slate-700 block mb-1">Select Vessel</label>}{<select className="w-full text-xs border border-slate-300 rounded p-2 bg-slate-50 outline-none max-w-xs">{<option>RV Bharati</option>}</select>}</div>}{<div>{<label className="text-[10px] font-bold text-slate-700 block mb-1">Date Range</label>}{<div className="flex items-center gap-2 max-w-xs text-xs">{<input type="text" className="flex-1 border border-slate-300 rounded p-1.5 bg-slate-50" defaultValue="01 Sep 2026"></input>}{<span className="text-slate-400">→</span>}{<input type="text" className="flex-1 border border-slate-300 rounded p-1.5 bg-slate-50" defaultValue="12 Sep 2026"></input>}</div>}</div>}{<div className="flex gap-3 pt-2">{<button className="bg-blue-600 text-white text-xs font-bold px-4 py-2 rounded hover:bg-blue-700">Generate Report</button>}</div>}</div>}</div>}{<div className="w-72 bg-white rounded-lg border border-slate-200 shadow-sm p-4 shrink-0 space-y-3">{<div className="text-xs font-bold text-slate-800 border-b border-slate-100 pb-2">Summary (RV Bharati)</div>}{<div className="space-y-2 text-[10px]">{[['Total Distance', '2,450 km'], ['Total Fuel Consumed', '320 MT'], ['Avg. Speed', '12.4 kn'], ['CO₂ Emissions (est.)', '1,020 MT'], ['Time in Ice (>60% SIC)', '36 hours']].map(([l, v]) => <div className="flex justify-between">{<span className="text-slate-500">{l}</span>}{<span className="font-bold text-slate-800">{v}</span>}</div>)}</div>}{<div className="pt-2 border-t border-slate-100 flex gap-2">{<select className="text-[10px] border border-slate-300 rounded p-1.5 bg-slate-50 flex-1 outline-none">{<option>PDF</option>}{<option>CSV</option>}</select>}{<button className="flex-1 flex items-center justify-center gap-1 bg-slate-700 text-white text-[10px] font-bold py-1.5 rounded hover:bg-slate-800">{<Download size={11}></Download>}Download</button>}</div>}</div>}</div>;
}
function OnshoreSettings() {
  const [tab, setTab] = (0, useState)('User Management');
  const tabs = ['User Management', 'System Configuration', 'Data Sources', 'Notifications'];
  const users = [{
    name: 'Admin User',
    role: 'Administrator',
    email: 'admin@domain.org',
    status: 'Active'
  }, {
    name: 'Route Analyst',
    role: 'Analyst',
    email: 'analyst@domain.org',
    status: 'Active'
  }, {
    name: 'Arvind Sharma',
    role: 'Operator',
    email: 'ops@domain.org',
    status: 'Active'
  }, {
    name: 'Research',
    role: 'Viewer',
    email: 'research@domain.org',
    status: 'Active'
  }];
  return <div className="flex flex-col h-full p-3 gap-3 bg-slate-100">{<div className="flex gap-2">{tabs.map(t => <button onClick={() => setTab(t)} className={cn('px-4 py-1.5 text-[10px] font-bold rounded-md', tab === t ? 'bg-blue-600 text-white' : 'bg-white text-slate-600 border border-slate-200 hover:bg-slate-50')}>{t}</button>)}</div>}{<div className="bg-white rounded-lg border border-slate-200 shadow-sm overflow-hidden flex-1 flex flex-col">{<table className="w-full text-[11px]">{<thead>{<tr className="bg-slate-50 border-b border-slate-200">{['Name', 'Role', 'Email', 'Status', ''].map(h => <th className="text-left px-4 py-2.5 font-bold text-slate-600 text-[10px]">{h}</th>)}</tr>}</thead>}{<tbody>{users.map((u, i) => <tr className="border-b border-slate-100 hover:bg-slate-50">{<td className="px-4 py-3 font-medium text-slate-800">{u.name}</td>}{<td className="px-4 py-3 text-slate-600">{u.role}</td>}{<td className="px-4 py-3 text-slate-500">{u.email}</td>}{<td className="px-4 py-3">{<span className="bg-green-100 text-green-700 text-[9px] font-bold px-2 py-0.5 rounded-full">{u.status}</span>}</td>}{<td className="px-4 py-3 flex items-center gap-2">{<button className="text-blue-500 hover:text-blue-700">{<Edit size={12}></Edit>}</button>}{<button className="text-red-400 hover:text-red-600">{<Trash2 size={12}></Trash2>}</button>}</td>}</tr>)}</tbody>}</table>}{<div className="p-4 border-t border-slate-100">{<button className="flex items-center gap-2 bg-blue-600 text-white text-[10px] font-bold px-4 py-2 rounded hover:bg-blue-700">{<Plus size={12}></Plus>}+ Add User</button>}</div>}</div>}</div>;
}
function OnshoreCommandCenter({
  onSwitchToOnboard
}) {
  const [tab, setTab] = (0, useState)('overview');
  const menuItems = [{
    id: 'overview',
    icon: <Layers size={15}></Layers>,
    label: 'Operational Overview'
  }, {
    id: 'vessels',
    icon: <Crosshair size={15}></Crosshair>,
    label: 'Vessel Tracking'
  }, {
    id: 'ice-weather',
    icon: <Thermometer size={15}></Thermometer>,
    label: 'Ice & Weather Monitoring'
  }, {
    id: 'route',
    icon: <Navigation size={15}></Navigation>,
    label: 'Route Planning'
  }, {
    id: 'iceberg',
    icon: <Map size={15}></Map>,
    label: 'Iceberg Tracking'
  }, {
    id: 'alerts',
    icon: <Bell size={15}></Bell>,
    label: 'Alerts & Notifications',
    badge: 3
  }, {
    id: 'data',
    icon: <BarChart2 size={15}></BarChart2>,
    label: 'Data & Forecasts'
  }, {
    id: 'reports',
    icon: <FileText size={15}></FileText>,
    label: 'Reports'
  }];
  const content = {
    overview: <OnshoreOverview></OnshoreOverview>,
    vessels: <OnshoreVessels></OnshoreVessels>,
    'ice-weather': <OnshoreIceWeather></OnshoreIceWeather>,
    route: <OnshoreRoute></OnshoreRoute>,
    iceberg: <OnshoreIceberg></OnshoreIceberg>,
    alerts: <OnshoreAlerts></OnshoreAlerts>,
    data: <OnshoreData></OnshoreData>,
    reports: <OnshoreReports></OnshoreReports>,
    settings: <OnshoreSettings></OnshoreSettings>
  };
  return <div className="flex flex-col h-full bg-slate-100 overflow-hidden">{<div className="h-12 bg-[#1e293b] text-white flex items-center justify-between px-4 shrink-0 shadow-md z-50">{<div className="flex items-center gap-6">{<div className="flex items-center gap-2">{<div className="w-7 h-7 bg-white rounded-full flex items-center justify-center text-[#1e293b] font-black text-sm">N</div>}{<div>{<div className="font-bold text-sm leading-tight">NCPOR</div>}{<div className="text-[8px] text-slate-400 leading-none">National Centre for Polar and Ocean Research · Ministry of Earth Sciences</div>}</div>}</div>}{<div className="h-5 w-px bg-slate-600"></div>}{<div className="flex gap-5 text-[11px] font-medium text-slate-300">{['Live View', 'Route Planning', 'Ice & Weather', 'Vessels', 'Analytics', 'Alerts', 'Reports'].map((t, i) => <span className={cn('flex items-center gap-1 cursor-pointer hover:text-white transition-colors', i === 0 && 'text-white')}>{t}</span>)}</div>}</div>}{<div className="flex items-center gap-3">{<button onClick={onSwitchToOnboard} className="text-[10px] font-bold flex items-center gap-1.5 bg-green-600 hover:bg-green-700 text-white px-3 py-1 rounded-full transition-colors">{<Ship size={11}></Ship>}Switch to Onboard</button>}{<div className="relative">{<Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400"></Search>}{<input className="bg-[#334155] text-[11px] text-white pl-8 pr-3 py-1.5 rounded w-56 border border-slate-600 focus:outline-none" placeholder="Search vessel, location..."></input>}</div>}{<div className="relative cursor-pointer">{<Bell size={16} className="text-slate-300"></Bell>}{<div className="absolute -top-1.5 -right-1.5 w-3 h-3 bg-red-500 rounded-full flex items-center justify-center text-[8px] text-white font-bold">3</div>}</div>}{<div className="w-7 h-7 bg-slate-600 rounded-full flex items-center justify-center cursor-pointer">{<User size={14}></User>}</div>}</div>}</div>}{<div className="flex flex-1 overflow-hidden">{<div className="w-52 bg-white border-r border-slate-200 flex flex-col shadow-sm z-40 shrink-0">{<div className="px-4 py-3 border-b border-slate-100 text-xs font-bold text-slate-800">Onshore Command Center</div>}{<div className="flex-1 py-2 overflow-y-auto">{menuItems.map(item => <button onClick={() => setTab(item.id)} className={cn('w-full flex items-center justify-between px-4 py-2.5 text-[11px] font-medium transition-colors', tab === item.id ? 'bg-blue-600 text-white' : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900')}>{<div className="flex items-center gap-2.5">{item.icon}{<span>{item.label}</span>}</div>}{item.badge && <span className="bg-red-500 text-white text-[9px] px-1.5 py-0.5 rounded-full font-bold">{item.badge}</span>}</button>)}</div>}{<div className="p-3 border-t border-slate-200">{<button onClick={() => setTab('settings')} className={cn('w-full flex items-center gap-2.5 px-4 py-2 text-[11px] font-medium rounded-md', tab === 'settings' ? 'bg-blue-600 text-white' : 'text-slate-600 hover:bg-slate-50')}>{<Settings size={15}></Settings>}{<span>Settings</span>}</button>}</div>}</div>}{<div className="flex-1 overflow-hidden">{content[tab] || content['overview']}</div>}</div>}</div>;
}
function OnboardNavigation() {
  return <div className="flex h-full p-3 gap-3 bg-[#0f172a]">{<div className="w-56 bg-[#1e293b] rounded-lg border border-slate-700 p-4 shrink-0 space-y-4 overflow-y-auto">{<div className="text-xs font-bold text-slate-300 border-b border-slate-700 pb-2">Vessel Information</div>}{<div className="flex items-center gap-3">{<div className="w-14 h-12 bg-slate-700 rounded shrink-0 overflow-hidden flex items-center justify-center">{<Ship size={20} className="text-slate-500"></Ship>}</div>}{<div>{<div className="text-sm font-bold text-white">RV Bharati</div>}{<div className="text-[10px] text-slate-400">Research Vessel</div>}</div>}</div>}{<div className="grid grid-cols-2 gap-1.5 text-[9px]">{[['IMO:', '9684012'], ['Call Sign:', 'VUAA'], ['MMSI:', '419001234'], ['Ice Class:', 'PC5'], ['Length:', '104 m'], ['Beam:', '18.0 m'], ['Draft:', '6.2 m'], ['Status:', 'Underway']].map(([l, v]) => <Unknown>{<span className="text-slate-500">{l}</span>}{<span className={cn('font-medium', l === 'Status:' ? 'text-green-400' : 'text-slate-300')}>{v}</span>}</Unknown>)}</div>}{<div className="border-t border-slate-700 pt-3">{<div className="text-xs font-bold text-slate-300 mb-3">Current Position</div>}{<div className="space-y-1.5 text-[10px]">{<div className="text-slate-300 font-bold">Lat: -66.247° / Lon: 72.341°</div>}{[['Speed:', '12.4 kn'], ['Heading:', '087°']].map(([l, v]) => <div className="flex gap-3">{<span className="text-slate-500 w-14">{l}</span>}{<span className="text-slate-200 font-bold">{v}</span>}</div>)}{<div className="mt-2 pt-2 border-t border-slate-700 space-y-1">{<div className="text-[9px] text-slate-500">Next Waypoint:</div>}{<div className="text-blue-400 font-bold text-xs">WP-12</div>}{<div className="text-[9px] text-slate-400">ETA: 14 Sep 2026, 06:20 UTC</div>}{<div className="text-[9px] text-slate-400">Distance: 420 nm</div>}</div>}</div>}</div>}</div>}{<div className="flex-1 relative rounded-lg overflow-hidden border border-slate-700 shadow-sm">{<SharedMap></SharedMap>}{<div className="absolute top-3 left-3 z-10 bg-[#1e293b]/95 text-[10px] text-slate-300 p-3 rounded-lg border border-slate-700 space-y-1.5 w-40">{[['w-4 h-px bg-green-500 border-dashed border-b-2', 'Planned Route'], ['w-4 h-px bg-blue-400 border-dashed border-b-2', 'Alternative Route'], ['w-3 h-3 rounded-sm border-2 border-blue-400 bg-transparent', 'Waypoints'], ['w-3 h-3 bg-white/60 rounded-sm border border-slate-400', 'Icebergs'], ['w-3 h-3 bg-blue-600 rounded-sm opacity-60', 'Sea Ice (SIC)']].map(([cls, label]) => <div className="flex items-center gap-2">{<div className={cls}></div>}{<span>{label}</span>}</div>)}</div>}{<div className="absolute top-1/2 left-1/2 -translate-x-1/2 bg-[#1e293b]/90 text-white text-[10px] p-2.5 rounded shadow-lg border border-slate-600 pointer-events-none w-52">{<div className="font-bold text-xs mb-1 text-blue-300">Sea Ice Concentration: 38%</div>}{<div className="space-y-0.5 text-slate-300">{<div>Ice Thickness: 0.8 m</div>}{<div>Iceberg Nearby: No</div>}{<div>Wind: 22 kn (SW)</div>}{<div>Air Temp: -11 °C</div>}</div>}</div>}</div>}{<div className="w-72 bg-[#1e293b] rounded-lg border border-slate-700 p-4 shrink-0 space-y-4 overflow-y-auto">{<div className="text-xs font-bold text-slate-300">Route Options (to Maitri Station)</div>}{<div className="text-[10px] text-slate-500">Select a recommended route:</div>}{<div className="bg-green-900/30 border border-green-700 rounded-lg p-3 space-y-2">{<div className="flex items-center gap-2 text-green-400 font-bold text-xs">{<span className="w-2 h-2 bg-green-500 rounded-full"></span>}Eco Route</div>}{<div className="text-[9px] text-slate-400">Lowest fuel consumption</div>}{<div className="flex justify-between text-[10px] text-slate-300 font-bold">{<span>⏱ 7.5 days</span>}{<span>⛽ 320 MT</span>}</div>}{<div className="text-[9px] text-slate-400">✓ Moderate ice</div>}{<button className="w-full bg-blue-600 text-white text-[10px] font-bold py-1.5 rounded hover:bg-blue-700">Select</button>}</div>}{<div className="grid grid-cols-2 gap-2">{[{
          label: 'Safest Route',
          sub: 'Avoids high ice concentration',
          days: '8.2 days',
          fuel: '340 MT',
          risk: '✓ Low risk',
          riskColor: 'text-green-400'
        }, {
          label: 'Fastest Route',
          sub: 'Minimum travel time',
          days: '5.9 days',
          fuel: '400 MT',
          risk: '⚠ Higher risk',
          riskColor: 'text-red-400'
        }].map(r => <div className="bg-[#0f172a] border border-slate-700 rounded-lg p-2.5 space-y-1.5">{<div className="text-blue-400 font-bold text-[10px]">{r.label}</div>}{<div className="text-[9px] text-slate-500">{r.sub}</div>}{<div className="text-[9px] text-slate-300 font-bold">{r.days} • {r.fuel}</div>}{<div className={cn('text-[9px]', r.riskColor)}>{r.risk}</div>}{<button className="w-full bg-blue-600 text-white text-[9px] font-bold py-1 rounded hover:bg-blue-700">Select</button>}</div>)}</div>}{<div className="border-t border-slate-700 pt-3">{<div className="text-xs font-bold text-slate-300 mb-3">Environmental Conditions</div>}{<div className="grid grid-cols-2 gap-3">{[{
            icon: <Layers size={12} className="text-blue-400"></Layers>,
            l: 'Sea Ice Concentration',
            v: '38%'
          }, {
            icon: <Wind size={12} className="text-sky-400"></Wind>,
            l: 'Wind Speed',
            v: '22 kn (SW)'
          }, {
            icon: <Thermometer size={12} className="text-cyan-400"></Thermometer>,
            l: 'Ice Thickness',
            v: '0.8 m'
          }, {
            icon: <Activity size={12} className="text-indigo-400"></Activity>,
            l: 'Wave Height',
            v: '1.4 m'
          }, {
            icon: <Thermometer size={12} className="text-red-400"></Thermometer>,
            l: 'Air Temperature',
            v: '-11 °C'
          }, {
            icon: <Eye size={12} className="text-slate-400"></Eye>,
            l: 'Visibility',
            v: 'Good'
          }].map((e, i) => <div className="flex gap-2 items-start">{e.icon}{<div>{<div className="text-[8px] text-slate-500">{e.l}</div>}{<div className="text-[10px] text-slate-200 font-bold">{e.v}</div>}</div>}</div>)}</div>}</div>}</div>}</div>;
}
function OnboardVesselStatus() {
  return <div className="flex flex-col h-full p-3 gap-3 bg-[#0f172a] overflow-y-auto">{<div className="text-xs font-bold text-slate-300 mb-1">Vessel Status</div>}{<div className="grid grid-cols-3 gap-3">{<div className="bg-[#1e293b] rounded-lg border border-slate-700 p-4">{<div className="text-[10px] font-bold text-slate-400 mb-3">RV Bharati — Research Vessel</div>}{<div className="flex items-center gap-3 mb-3">{<div className="w-20 h-14 bg-slate-700 rounded overflow-hidden flex items-center justify-center shrink-0">{<Ship size={24} className="text-slate-500"></Ship>}</div>}{<div className="space-y-1 text-[9px]">{[['IMO:', '9684012'], ['MMSI:', '419001234'], ['Call Sign:', 'VUAA'], ['Ice Class:', 'PC5'], ['Length:', '104 m'], ['Beam:', '18.0 m'], ['Draft:', '6.2 m']].map(([l, v]) => <div className="flex gap-2">{<span className="text-slate-500 w-16">{l}</span>}{<span className="text-slate-300 font-medium">{v}</span>}</div>)}</div>}</div>}{<div className="bg-green-900/30 border border-green-700 text-green-400 text-[9px] font-bold px-2 py-0.5 rounded-full inline-block">Underway</div>}</div>}{<div className="bg-[#1e293b] rounded-lg border border-slate-700 p-4">{<div className="text-[10px] font-bold text-slate-400 mb-3">Current Position</div>}{<div className="space-y-2 text-[10px]">{[['Lat:', '-66.247°'], ['Lon:', '72.341°'], ['Speed:', '12.4 kn'], ['Heading:', '087°']].map(([l, v]) => <div className="flex justify-between">{<span className="text-slate-500">{l}</span>}{<span className="text-slate-200 font-bold">{v}</span>}</div>)}{<div className="border-t border-slate-700 pt-2 space-y-1">{<div className="flex justify-between">{<span className="text-slate-500">Next Waypoint</span>}{<span className="text-blue-400 font-bold">WP-12</span>}</div>}{<div className="flex justify-between">{<span className="text-slate-500">ETA</span>}{<span className="text-slate-200 text-[9px]">14 Sep 2026, 06:20 UTC</span>}</div>}{<div className="flex justify-between">{<span className="text-slate-500">Distance to WP</span>}{<span className="text-slate-200 font-bold">420 nm</span>}</div>}</div>}</div>}</div>}{<div className="bg-[#1e293b] rounded-lg border border-slate-700 p-4 flex flex-col items-center">{<div className="text-[10px] font-bold text-slate-400 mb-3 self-start">Engine Load</div>}{<div className="relative w-32 h-32 my-2">{<svg className="w-full h-full -rotate-90" viewBox="0 0 36 36">{<path strokeWidth="3" stroke="#334155" fill="none" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"></path>}{<path strokeWidth="3" strokeDasharray="78, 100" stroke="#3b82f6" fill="none" strokeLinecap="round" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"></path>}</svg>}{<div className="absolute inset-0 flex flex-col items-center justify-center">{<span className="text-3xl font-black text-white">78%</span>}</div>}</div>}{<div className="text-[9px] text-slate-400 text-center">Fuel Consumption</div>}{<div className="text-lg font-black text-white">3.2 MT/day</div>}</div>}</div>}{<div className="grid grid-cols-4 gap-3">{[{
        label: 'Main Engine',
        val: 'Running',
        color: 'text-green-400',
        sub: 'RPM: 78  Power Output: 12.6 MW'
      }, {
        label: 'Fuel Level',
        val: '65%',
        color: 'text-blue-400',
        sub: 'Remaining: 18 days  Total Capacity: 500 m³'
      }, {
        label: 'Hull Temperature',
        val: '-5 °C',
        color: 'text-cyan-400',
        sub: '(Normal)'
      }, {
        label: 'GPS Status',
        val: 'Healthy',
        color: 'text-green-400',
        sub: '12 Satellites'
      }].map(s => <div className="bg-[#1e293b] rounded-lg border border-slate-700 p-3">{<div className="text-[9px] text-slate-500 mb-1">{s.label}</div>}{<div className={cn('text-sm font-bold', s.color)}>{s.val}</div>}{<div className="text-[8px] text-slate-600 mt-1">{s.sub}</div>}</div>)}</div>}{<div className="grid grid-cols-2 gap-3 flex-1">{<div className="bg-[#1e293b] rounded-lg border border-slate-700 p-4">{<div className="text-[10px] font-bold text-slate-400 mb-2">Speed & Fuel Consumption (Last 24 Hours)</div>}{<div className="h-24 bg-[#0f172a] rounded p-2 relative overflow-hidden">{<svg className="w-full h-full" viewBox="0 0 200 60" preserveAspectRatio="none">{<polyline fill="none" stroke="#3b82f6" strokeWidth="1.5" points="0,30 30,25 60,20 90,28 120,15 150,22 180,18 200,20"></polyline>}{<polyline fill="none" stroke="#22c55e" strokeWidth="1.5" strokeDasharray="3,2" points="0,40 30,38 60,45 90,35 120,50 150,40 180,38 200,42"></polyline>}</svg>}</div>}{<div className="flex gap-4 text-[9px] mt-2">{<div className="flex items-center gap-1">{<div className="w-3 h-px bg-blue-500"></div>}{<span className="text-slate-400">Speed (kn)</span>}</div>}{<div className="flex items-center gap-1">{<div className="w-3 h-px bg-green-500 border-dashed border-b"></div>}{<span className="text-slate-400">Fuel Consumption (MT/day)</span>}</div>}</div>}</div>}{<div className="bg-[#1e293b] rounded-lg border border-slate-700 p-4">{<div className="text-[10px] font-bold text-slate-400 mb-3">System Health</div>}{<div className="space-y-2">{['Propulsion System', 'Steering System', 'Power Generation', 'Navigation Sensors', 'Communication', 'Ice Detection Radar'].map(s => <div className="flex items-center justify-between text-[10px]">{<span className="text-slate-400">{s}</span>}{<div className="flex items-center gap-1.5">{<div className="w-2 h-2 bg-green-500 rounded-full"></div>}{<span className="text-green-400 font-medium">Normal</span>}</div>}</div>)}</div>}</div>}</div>}</div>;
}
function OnboardWaypointsPanel() {
  const waypoints = [{
    num: 'WP-10',
    lat: '72.341°',
    lon: '66.441°',
    eta: '12 Sep 10:00',
    status: 'Passed',
    color: 'text-slate-500'
  }, {
    num: 'WP-11',
    lat: '-45.764°',
    lon: '71.841°',
    eta: '13 Sep 06:00',
    status: 'Passed',
    color: 'text-slate-500'
  }, {
    num: 'WP-12',
    lat: '-66.247°',
    lon: '72.341°',
    eta: '14 Sep 06:20',
    status: 'Next',
    color: 'text-blue-400',
    active: true
  }, {
    num: 'WP-13',
    lat: '-66.44°',
    lon: '71.11°',
    eta: '15 Sep 08:00',
    status: 'Pending',
    color: 'text-slate-400'
  }, {
    num: 'Maitri Station',
    lat: '-67.612°',
    lon: '73.99°',
    eta: '16 Sep 10:00',
    status: 'Dest.',
    color: 'text-green-400'
  }];
  return <div className="flex h-full p-3 gap-3 bg-[#0f172a]">{<div className="w-72 bg-[#1e293b] rounded-lg border border-slate-700 flex flex-col shrink-0">{<div className="p-3 border-b border-slate-700 text-xs font-bold text-slate-300">Waypoints</div>}{<div className="flex-1 overflow-y-auto">{<table className="w-full text-[9px]">{<thead>{<tr className="bg-[#0f172a] border-b border-slate-700">{['#', 'Lat', 'Lon', 'ETA', 'Status'].map(h => <th className="text-left px-2 py-2 text-slate-500 font-bold">{h}</th>)}</tr>}</thead>}{<tbody>{waypoints.map((w, i) => <tr className={cn('border-b border-slate-800', w.active && 'bg-blue-900/30')}>{<td className={cn('px-2 py-2.5 font-bold', w.color)}>{w.num}</td>}{<td className="px-2 py-2.5 text-slate-400">{w.lat}</td>}{<td className="px-2 py-2.5 text-slate-400">{w.lon}</td>}{<td className="px-2 py-2.5 text-slate-400 text-[8px]">{w.eta}</td>}{<td className={cn('px-2 py-2.5 font-bold text-[8px]', w.color)}>{w.status}</td>}</tr>)}</tbody>}</table>}</div>}{<div className="p-3 flex gap-2">{<button className="flex-1 bg-blue-600 text-white text-[10px] font-bold py-1.5 rounded hover:bg-blue-700">Add Waypoint</button>}{<button className="flex-1 bg-[#0f172a] border border-slate-600 text-slate-300 text-[10px] font-bold py-1.5 rounded hover:bg-slate-800">Edit Route</button>}{<button className="flex-1 bg-red-900/50 border border-red-800 text-red-400 text-[10px] font-bold py-1.5 rounded hover:bg-red-900">Clear Route</button>}</div>}</div>}{<div className="flex-1 relative rounded-lg overflow-hidden border border-slate-700 shadow-sm">{<SharedMap zoom={4.5} center={[72.341, -66.247]}></SharedMap>}</div>}</div>;
}
function OnboardWeatherIce() {
  const [tab, setTab] = (0, useState)('Current Conditions');
  return <div className="flex h-full p-3 gap-3 bg-[#0f172a]">{<div className="flex-1 flex flex-col gap-3">{<div className="flex gap-2">{['Current Conditions', 'Forecast (7 Days)'].map(t => <button onClick={() => setTab(t)} className={cn('px-4 py-1.5 text-[10px] font-bold rounded-md', tab === t ? 'bg-blue-600 text-white' : 'bg-[#1e293b] text-slate-400 border border-slate-700 hover:bg-slate-800')}>{t}</button>)}</div>}{<div className="grid grid-cols-3 gap-3">{[{
          icon: <Layers size={18} className="text-blue-400"></Layers>,
          l: 'Sea Ice Concentration',
          v: '38%'
        }, {
          icon: <Thermometer size={18} className="text-cyan-400"></Thermometer>,
          l: 'Ice Thickness',
          v: '0.8 m'
        }, {
          icon: <Thermometer size={18} className="text-red-400"></Thermometer>,
          l: 'Air Temperature',
          v: '-11 °C'
        }, {
          icon: <Wind size={18} className="text-sky-400"></Wind>,
          l: 'Wind Speed',
          v: '22 kn (SW)'
        }, {
          icon: <Activity size={18} className="text-indigo-400"></Activity>,
          l: 'Wave Height',
          v: '1.4 m'
        }, {
          icon: <Eye size={18} className="text-slate-400"></Eye>,
          l: 'Visibility',
          v: 'Good'
        }].map((k, i) => <div className="bg-[#1e293b] rounded-lg border border-slate-700 p-3 flex items-center gap-3">{k.icon}{<div>{<div className="text-[9px] text-slate-500">{k.l}</div>}{<div className="text-lg font-black text-white">{k.v}</div>}</div>}</div>)}</div>}{<div className="flex-1 relative rounded-lg overflow-hidden border border-slate-700">{<SharedMap></SharedMap>}</div>}</div>}</div>;
}
function OnboardAlerts() {
  const [tab, setTab] = (0, useState)('All Alerts');
  const tabs = ['All Alerts (5)', 'Navigation (2)', 'Ice & Weather (1)', 'System (1)', 'Communication (1)'];
  const alerts = [{
    time: '10:32',
    type: 'Iceberg',
    sev: 'High',
    sevColor: 'bg-red-500',
    msg: 'Potential iceberg intersection in 12 hours',
    loc: 'Lat -66.812° Lon 71.998°',
    status: 'Open',
    statusColor: 'bg-red-500'
  }, {
    time: '08:14',
    type: 'Sea Ice',
    sev: 'Medium',
    sevColor: 'bg-orange-400',
    msg: 'High ice concentration ahead (>85% SIC)',
    loc: 'Ahead (50 nm)',
    status: 'Acknowledged',
    statusColor: 'bg-slate-600'
  }, {
    time: '06:03',
    type: 'Weather',
    sev: 'Low',
    sevColor: 'bg-blue-500',
    msg: 'Strong winds (45 kn) expected in your area',
    loc: 'Lat -67.104° Lon 73.221°',
    status: 'Open',
    statusColor: 'bg-red-500'
  }, {
    time: 'Yesterday 22:18',
    type: 'System',
    sev: 'Medium',
    sevColor: 'bg-orange-400',
    msg: 'Main engine exhaust temperature high',
    loc: 'Engine Room',
    status: 'Resolved',
    statusColor: 'bg-green-700'
  }, {
    time: 'Yesterday 14:37',
    type: 'Communication',
    sev: 'Low',
    sevColor: 'bg-blue-500',
    msg: 'VSAT signal degraded',
    loc: '—',
    status: 'Resolved',
    statusColor: 'bg-green-700'
  }];
  const [selected, setSelected] = (0, useState)(0);
  return <div className="flex flex-col h-full p-3 gap-3 bg-[#0f172a]">{<div className="text-xs font-bold text-slate-300">Alerts & Notifications</div>}{<div className="flex gap-2 flex-wrap">{tabs.map(t => <button onClick={() => setTab(t)} className={cn('px-3 py-1 text-[9px] font-bold rounded-md', tab === t ? 'bg-blue-600 text-white' : 'bg-[#1e293b] border border-slate-700 text-slate-400 hover:bg-slate-800')}>{t}</button>)}{<div className="ml-auto flex items-center gap-1 text-[9px] text-slate-400">{<Filter size={10}></Filter>}Filter: All</div>}</div>}{<div className="flex flex-1 gap-3 min-h-0">{<div className="flex-[2] bg-[#1e293b] rounded-lg border border-slate-700 overflow-hidden flex flex-col">{<table className="w-full text-[10px]">{<thead>{<tr className="bg-[#0f172a] border-b border-slate-700">{['Time (UTC)', 'Type', 'Severity', 'Message', 'Location / Details', 'Status', 'Action'].map(h => <th className="text-left px-3 py-2 text-slate-500 font-bold text-[9px]">{h}</th>)}</tr>}</thead>}{<tbody>{alerts.map((a, i) => <tr onClick={() => setSelected(i)} className={cn('border-b border-slate-800 cursor-pointer', selected === i ? 'bg-blue-900/30' : 'hover:bg-slate-800/50')}>{<td className="px-3 py-2.5 text-slate-500 text-[9px]">{a.time}</td>}{<td className="px-3 py-2.5">{<div className="flex items-center gap-1">{<AlertTriangle size={10} className="text-orange-400"></AlertTriangle>}{<span className="text-slate-300 font-medium">{a.type}</span>}</div>}</td>}{<td className="px-3 py-2.5">{<span className={cn('text-white px-1.5 py-0.5 rounded-full font-bold text-[9px]', a.sevColor)}>{a.sev}</span>}</td>}{<td className="px-3 py-2.5 text-slate-400 text-[9px] max-w-[200px]">{a.msg}</td>}{<td className="px-3 py-2.5 text-slate-500 text-[9px]">{a.loc}</td>}{<td className="px-3 py-2.5">{<span className={cn('text-white px-1.5 py-0.5 rounded-full font-bold text-[9px]', a.statusColor)}>{a.status}</span>}</td>}{<td className="px-3 py-2.5">{<button className="text-blue-400 font-bold text-[9px] hover:underline">View</button>}</td>}</tr>)}</tbody>}</table>}</div>}{<div className="w-56 bg-[#1e293b] rounded-lg border border-slate-700 p-3 flex flex-col gap-2 shrink-0">{<div className="text-[10px] font-bold text-slate-300 border-b border-slate-700 pb-2">Selected Alert Details</div>}{<div className="flex items-start gap-2 bg-red-900/30 border border-red-800 rounded p-2">{<AlertTriangle size={12} className="text-red-400 shrink-0 mt-0.5"></AlertTriangle>}{<span className="text-[9px] text-red-300 font-bold leading-tight">{alerts[selected].msg}</span>}</div>}{<div className="space-y-1.5 text-[9px]">{[['Time (UTC):', alerts[selected].time], ['Location:', alerts[selected].loc], ['Details:', 'Forecasted Iceberg A-7421 crosses current route. CPA: 2.1 nm at 22:14 UTC.'], ['Recommended Action:', 'Consider course alteration (auto route suggestion available).']].map(([l, v]) => <div>{<div className="text-slate-500 font-bold">{l}</div>}{<div className="text-slate-300 mt-0.5">{v}</div>}</div>)}</div>}{<div className="h-24 bg-[#0f172a] rounded overflow-hidden relative mt-1">{<div className="absolute inset-0 bg-gradient-to-b from-blue-800/30 to-red-800/30"></div>}</div>}{<div className="flex gap-2">{<button className="flex-1 bg-blue-600 text-white text-[9px] font-bold py-1.5 rounded hover:bg-blue-700">View on Map</button>}{<button className="flex-1 bg-[#0f172a] border border-slate-600 text-slate-300 text-[9px] font-bold py-1.5 rounded hover:bg-slate-800">Recalculate Route</button>}</div>}</div>}</div>}</div>;
}
function OnboardCommunications() {
  const messages = [{
    from: 'Onshore Command',
    preview: 'Route update acknowledged',
    time: '10:25',
    unread: true
  }, {
    from: 'Weather Center',
    preview: 'Polar weather advisory - Sector B',
    time: '08:14'
  }, {
    from: 'SA Agulhas II',
    preview: 'Position report',
    time: '06:52'
  }, {
    from: 'Onshore Command',
    preview: 'New waypoints received',
    time: 'Yesterday'
  }, {
    from: 'Logistics',
    preview: 'Fuel and supplies update',
    time: 'Yesterday'
  }, {
    from: 'Technical Support',
    preview: 'System check completed',
    time: '10 Sep'
  }, {
    from: 'RV M.V. Explorer',
    preview: 'Re: Ice conditions',
    time: '10 Sep'
  }];
  return <div className="flex h-full p-3 gap-3 bg-[#0f172a]">{<div className="flex-1 flex flex-col gap-3">{<div className="flex items-center justify-between">{<div className="flex gap-2">{['Message Center', 'Compose Message', 'File Transfer', 'Contacts'].map((t, i) => <button className={cn('px-3 py-1.5 text-[10px] font-bold rounded-md', i === 0 ? 'bg-blue-600 text-white' : 'bg-[#1e293b] border border-slate-700 text-slate-400 hover:bg-slate-800')}>{t}</button>)}</div>}{<div className="flex items-center gap-2 text-[10px] text-slate-400">{<div className="w-2 h-2 bg-green-500 rounded-full"></div>}VSAT Online{<span className="ml-2 text-slate-500">Bandwidth: 256 kbps</span>}</div>}</div>}{<div className="flex flex-1 gap-3 min-h-0">{<div className="w-72 bg-[#1e293b] rounded-lg border border-slate-700 flex flex-col shrink-0">{<div className="p-2 border-b border-slate-700">{<div className="relative">{<Search size={11} className="absolute left-2 top-1/2 -translate-y-1/2 text-slate-500"></Search>}{<input className="w-full bg-[#0f172a] border border-slate-700 rounded text-[10px] text-slate-300 pl-7 pr-2 py-1.5 focus:outline-none" placeholder="Search messages..."></input>}</div>}</div>}{<div className="flex-1 overflow-y-auto">{messages.map((m, i) => <div className={cn('p-3 border-b border-slate-800 cursor-pointer hover:bg-slate-800/50', i === 0 && 'bg-blue-900/30')}>{<div className="flex justify-between items-start">{<div className="flex items-center gap-1.5">{<div className={cn('w-7 h-7 rounded-full flex items-center justify-center text-[10px] font-bold text-white shrink-0', i === 0 ? 'bg-blue-600' : i === 2 ? 'bg-green-700' : 'bg-slate-600')}>{m.from[0]}</div>}{<span className={cn('text-[10px] font-bold', m.unread ? 'text-white' : 'text-slate-400')}>{m.from}</span>}</div>}{<span className="text-[8px] text-slate-500 shrink-0">{m.time}</span>}</div>}{<div className="text-[9px] text-slate-500 mt-1 pl-9 truncate">{m.preview}</div>}</div>)}</div>}</div>}{<div className="flex-1 bg-[#1e293b] rounded-lg border border-slate-700 p-5 flex flex-col">{<div className="space-y-1 text-[10px] text-slate-400 border-b border-slate-700 pb-3 mb-4">{[['From:', 'Onshore Command'], ['To:', 'RV Bharati'], ['Time:', '12 Sep 2026, 10:10 UTC'], ['Subject:', 'Route update acknowledged']].map(([l, v]) => <div className="flex gap-3">{<span className="w-16 text-slate-500">{l}</span>}{<span className={l === 'Subject:' ? 'text-white font-bold' : 'text-slate-300'}>{v}</span>}</div>)}</div>}{<div className="flex-1 text-[11px] text-slate-300 leading-relaxed">{<p>Dear Crew,</p>}{<p className="mt-3">The latest position report has been received. The route deviation due to the iceberg threat is approved. Please continue to monitor ice conditions and send the next position update at 14:00 UTC.</p>}{<p className="mt-3">Safe sailing,{<br></br>}Onshore Operations Team</p>}</div>}{<div className="flex gap-2 mt-4 border-t border-slate-700 pt-4">{['Reply', 'Reply All', 'Forward', 'Archive'].map(a => <button className={cn('px-4 py-1.5 text-[10px] font-bold rounded', a === 'Reply' ? 'bg-blue-600 text-white hover:bg-blue-700' : 'bg-[#0f172a] border border-slate-700 text-slate-300 hover:bg-slate-800')}>{a}</button>)}</div>}</div>}</div>}</div>}</div>;
}
function OnboardSettings() {
  const [tab, setTab] = (0, useState)('General');
  const tabs = ['General', 'Navigation', 'Alerts', 'Communication', 'Units', 'System'];
  return <div className="flex flex-col h-full p-3 gap-3 bg-[#0f172a]">{<div className="flex gap-2">{tabs.map(t => <button onClick={() => setTab(t)} className={cn('px-3 py-1.5 text-[10px] font-bold rounded-md', tab === t ? 'bg-blue-600 text-white' : 'bg-[#1e293b] border border-slate-700 text-slate-400 hover:bg-slate-800')}>{t}</button>)}</div>}{<div className="flex flex-1 gap-3 min-h-0">{<div className="w-72 bg-[#1e293b] rounded-lg border border-slate-700 p-4 shrink-0 space-y-3">{<div className="text-[10px] font-bold text-slate-300 border-b border-slate-700 pb-2">Vessel Information</div>}{[['Vessel Name', 'RV Bharati'], ['MMSI', '419001234'], ['Call Sign', 'VUAA'], ['Ice Class', 'PC5'], ['Default Draft (m)', '6.2'], ['Max Speed (kn)', '16']].map(([l, v]) => <div>{<label className="text-[9px] text-slate-500 block mb-0.5">{l}</label>}{<input className="w-full bg-[#0f172a] border border-slate-700 rounded text-[11px] text-slate-300 px-2 py-1.5 focus:outline-none" defaultValue={v}></input>}</div>)}</div>}{<div className="w-72 bg-[#1e293b] rounded-lg border border-slate-700 p-4 shrink-0 space-y-3">{<div className="text-[10px] font-bold text-slate-300 border-b border-slate-700 pb-2">Display Preferences</div>}{[['Map Theme', 'Light'], ['Chart Layer', 'Satellite (Ice)'], ['Distance Unit', 'Nautical Miles (nm)'], ['Temperature Unit', 'Celsius (°C)']].map(([l, v]) => <div>{<label className="text-[9px] text-slate-500 block mb-0.5">{l}</label>}{<select className="w-full bg-[#0f172a] border border-slate-700 rounded text-[11px] text-slate-300 px-2 py-1.5 focus:outline-none">{<option>{v}</option>}</select>}</div>)}{<div className="space-y-2">{['Show Icebergs', 'Show Sea Ice Concentration', 'Show Weather Overlay', 'Show Vessel Track'].map(s => <label className="flex items-center justify-between cursor-pointer">{<span className="text-[10px] text-slate-400">{s}</span>}{<div className="w-8 h-4 bg-blue-600 rounded-full relative">{<div className="absolute right-0.5 top-0.5 w-3 h-3 bg-white rounded-full shadow"></div>}</div>}</label>)}</div>}</div>}{<div className="flex-1 bg-[#1e293b] rounded-lg border border-slate-700 p-4 space-y-3">{<div className="text-[10px] font-bold text-slate-300 border-b border-slate-700 pb-2">System</div>}{[['Language', 'English'], ['Time Zone', 'UTC']].map(([l, v]) => <div>{<label className="text-[9px] text-slate-500 block mb-0.5">{l}</label>}{<select className="w-full bg-[#0f172a] border border-slate-700 rounded text-[11px] text-slate-300 px-2 py-1.5 focus:outline-none">{<option>{v}</option>}</select>}</div>)}{['Auto Sync Time', 'Data Auto-Update', 'Offline Mode'].map(s => <label className="flex items-center justify-between cursor-pointer">{<span className="text-[10px] text-slate-400">{s}</span>}{<div className="w-8 h-4 bg-blue-600 rounded-full relative">{<div className="absolute right-0.5 top-0.5 w-3 h-3 bg-white rounded-full shadow"></div>}</div>}</label>)}{<div className="border-t border-slate-700 pt-3">{<div className="text-[10px] font-bold text-slate-300 mb-2">Data Sources</div>}{[['Satellite (Copernicus)', 'Connected'], ['Iceberg Forecast (NSIDC)', 'Connected'], ['Weather (ECMWF)', 'Connected']].map(([s, v]) => <div className="flex items-center justify-between text-[9px] mb-1.5">{<span className="text-slate-400">{s}</span>}{<div className="flex items-center gap-1">{<div className="w-1.5 h-1.5 bg-green-500 rounded-full"></div>}{<span className="text-green-400 font-bold">{v}</span>}</div>}</div>)}</div>}{<div className="pt-3 flex gap-2">{<button className="flex-1 bg-[#0f172a] border border-slate-700 text-slate-300 text-[10px] font-bold py-2 rounded hover:bg-slate-800">Save Changes</button>}{<button className="flex-1 bg-red-900/50 border border-red-800 text-red-400 text-[10px] font-bold py-2 rounded hover:bg-red-900">Reset to Default</button>}</div>}</div>}</div>}</div>;
}
function OnboardPanel({
  onSwitchToOnshore
}) {
  const [tab, setTab] = (0, useState)('nav');
  const menuItems = [{
    id: 'nav',
    icon: <Crosshair size={14}></Crosshair>,
    label: 'Navigation'
  }, {
    id: 'waypoints',
    icon: <Navigation size={14}></Navigation>,
    label: 'Route & Waypoints'
  }, {
    id: 'weather',
    icon: <Thermometer size={14}></Thermometer>,
    label: 'Weather & Ice'
  }, {
    id: 'vessel-status',
    icon: <Activity size={14}></Activity>,
    label: 'Vessel Status'
  }, {
    id: 'alerts',
    icon: <Bell size={14}></Bell>,
    label: 'Alerts',
    badge: 2
  }, {
    id: 'comms',
    icon: <MessageSquare size={14}></MessageSquare>,
    label: 'Communications'
  }, {
    id: 'logs',
    icon: <BookOpen size={14}></BookOpen>,
    label: 'Logs'
  }, {
    id: 'settings',
    icon: <Settings size={14}></Settings>,
    label: 'Settings'
  }];
  const content = {
    nav: <OnboardNavigation></OnboardNavigation>,
    waypoints: <OnboardWaypointsPanel></OnboardWaypointsPanel>,
    weather: <OnboardWeatherIce></OnboardWeatherIce>,
    'vessel-status': <OnboardVesselStatus></OnboardVesselStatus>,
    alerts: <OnboardAlerts></OnboardAlerts>,
    comms: <OnboardCommunications></OnboardCommunications>,
    logs: <div className="flex items-center justify-center h-full bg-[#0f172a] text-slate-500 flex-col gap-2">{<BookOpen size={36} className="opacity-20"></BookOpen>}{<p className="text-sm">Voyage Logs — Coming Soon</p>}</div>,
    settings: <OnboardSettings></OnboardSettings>
  };
  return <div className="flex flex-col h-full bg-[#0f172a] overflow-hidden">{<div className="h-12 bg-[#172554] text-white flex items-center justify-between px-4 shrink-0 shadow-md z-50">{<div className="flex items-center gap-6">{<div className="flex items-center gap-2">{<Ship size={18} className="text-blue-300"></Ship>}{<div>{<div className="font-bold text-sm leading-tight">SHIP (ONBOARD) PANEL</div>}</div>}</div>}{<div className="h-4 w-px bg-slate-600"></div>}{<span className="text-xs text-slate-300">RV Bharati</span>}{<div className="flex items-center gap-1.5 text-[10px]">{<div className="w-2 h-2 bg-green-400 rounded-full shadow-[0_0_4px_#4ade80]"></div>}{<span className="text-green-300 font-medium">Online</span>}</div>}{<div className="flex gap-5 text-[11px] text-slate-400">{['Navigate Safely', 'Stay Informed', 'Report'].map((t, i) => <Unknown>{<span className="cursor-pointer hover:text-white">{t}</span>}{i < 2 && <span>•</span>}</Unknown>)}</div>}</div>}{<div className="flex items-center gap-5 text-[11px] text-slate-300">{<span>12 Sep 2026 | 10:45 UTC</span>}{<div className="flex items-center gap-1">{<div className="w-2 h-2 bg-green-500 rounded-full"></div>}{<span className="text-[10px]">VSAT</span>}</div>}{<button onClick={onSwitchToOnshore} className="text-[10px] font-bold flex items-center gap-1.5 bg-blue-700 hover:bg-blue-800 text-white px-3 py-1 rounded-full transition-colors">{<MonitorSmartphone size={11}></MonitorSmartphone>}Switch to Onshore</button>}{<div className="w-7 h-7 bg-white/10 rounded-full flex items-center justify-center cursor-pointer">{<User size={14}></User>}</div>}</div>}</div>}{<div className="flex flex-1 overflow-hidden">{<div className="w-44 bg-[#1e293b] border-r border-slate-700 flex flex-col shrink-0 z-40">{<div className="flex-1 py-4 space-y-0.5">{menuItems.map(item => <button onClick={() => setTab(item.id)} className={cn('w-full flex items-center justify-between px-4 py-3 text-[11px] font-medium transition-colors', tab === item.id ? 'bg-[#334155] text-white border-l-4 border-blue-400' : 'text-slate-400 hover:bg-[#334155] hover:text-white border-l-4 border-transparent')}>{<div className="flex items-center gap-2.5">{item.icon}{<span>{item.label}</span>}</div>}{item.badge && <span className="bg-red-500 text-white text-[9px] px-1.5 py-0.5 rounded-full font-bold">{item.badge}</span>}</button>)}</div>}</div>}{<div className="flex-1 overflow-hidden">{content[tab] || content['nav']}</div>}</div>}</div>;
}
function Dashboard() {
  const [view, setView] = (0, useState)('onshore');
  return <div className="h-screen w-full bg-slate-900 overflow-hidden font-sans">{view === 'onshore' ? <OnshoreCommandCenter onSwitchToOnboard={() => setView('onboard')}></OnshoreCommandCenter> : <OnboardPanel onSwitchToOnshore={() => setView('onshore')}></OnboardPanel>}</div>;
}