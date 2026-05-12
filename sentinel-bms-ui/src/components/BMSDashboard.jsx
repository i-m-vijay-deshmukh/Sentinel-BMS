import React, { useState, useEffect } from 'react';
import { Battery, Zap, Thermometer, Activity, Cpu, Power, AlertTriangle } from 'lucide-react';

const BMSDashboard = () => {
  const [data, setData] = useState({
    cell1: 0, cell2: 0, cell3: 0, 
    current: 0, temp: 0, 
    charging: false, soh: 100,
    discharge_active: true
  });
  const [connectionError, setConnectionError] = useState(null);

  const LIMITS = { MAX_TEMP: 45.0, MIN_SOH: 80.0, MAX_CELL_V: 4.25, MIN_CELL_V: 3.00 };
  const API_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

  useEffect(() => {
    const fetchData = async () => {
      try {
        const response = await fetch(`${API_URL}/api/react_pull`);
        if (!response.ok) throw new Error('Offline');
        const json = await response.json();
        setData(json);
        setConnectionError(null);
      } catch (err) {
        setConnectionError("Connection Lost: Check Middleware");
      }
    };
    const interval = setInterval(fetchData, 2000);
    return () => clearInterval(interval);
  }, [API_URL]);

  const handleDischargeToggle = async () => {
    if (data.charging) return; // Prevent manual override while charging
    const newState = !data.discharge_active;
    try {
      await fetch(`${API_URL}/api/toggle_power`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ discharge_active: newState })
      });
    } catch (err) {
      console.error("Toggle request failed");
    }
  };

  const totalVoltage = data.cell1 + data.cell2 + data.cell3;
  const soc = Math.max(0, Math.min(100, (((totalVoltage / 3) - 3.0) / 1.2) * 100));

  return (
    <div className="min-h-screen bg-[#020617] text-slate-100 p-4 md:p-8 font-sans selection:bg-blue-500/30">
      
      {/* HEADER: Dynamic Alerts & Power Control */}
      <header className="mb-8 flex flex-col md:flex-row justify-between items-start md:items-center gap-4 border-b border-slate-800/60 pb-6">
        <div className="flex items-center gap-4">
          <div className="bg-blue-500/10 p-3 rounded-2xl border border-blue-500/20">
            <Cpu className="text-blue-500" size={28} />
          </div>
          <div>
            <h1 className="text-3xl font-black tracking-tighter text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-indigo-500">
              SENTINEL-BMS <span className="text-slate-600 font-light text-xl">PRO</span>
            </h1>
            <p className="text-slate-500 text-xs mt-1 uppercase tracking-[0.2em] font-bold">3S 5000mAh EV Architecture</p>
          </div>
        </div>
        
        <div className="flex items-center gap-4">
          {data.charging && (
            <div className="flex items-center gap-2 px-4 py-2 bg-amber-500/10 border border-amber-500/50 rounded-xl text-amber-500 animate-pulse">
              <AlertTriangle size={18} />
              <span className="text-xs font-black uppercase">Charging: Output Disabled</span>
            </div>
          )}

          <div className="flex items-center gap-3 bg-slate-900/50 p-1.5 rounded-2xl border border-slate-800">
            <span className="text-[10px] font-bold text-slate-500 ml-2 uppercase tracking-tighter">Power Out</span>
            <button 
              onClick={handleDischargeToggle}
              disabled={data.charging}
              className={`flex items-center gap-2 px-5 py-2 rounded-xl text-xs font-black transition-all duration-500 ${data.discharge_active ? 'bg-blue-600 text-white shadow-[0_0_20px_rgba(37,99,235,0.4)]' : 'bg-slate-800 text-slate-500'} ${data.charging ? 'opacity-50 cursor-not-allowed' : ''}`}
            >
              <Power size={14} />
              {data.discharge_active ? "ON" : "OFF"}
            </button>
          </div>
        </div>
      </header>

      {/* PRIMARY METRICS */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 mb-6">
        <div className="lg:col-span-3 flex flex-col gap-6">
          <MetricPanel title="Charge Level" value={soc.toFixed(1)} unit="%" icon={<Battery />} color="text-blue-400" />
          <MetricPanel title="Live Power" value={(totalVoltage * Math.abs(data.current)).toFixed(1)} unit="W" icon={<Zap />} color="text-yellow-400" />
        </div>

        {/* THERMAL CONSOLE */}
        <div className={`lg:col-span-6 relative bg-slate-900/40 rounded-[2rem] border p-8 flex flex-col items-center justify-center transition-all ${data.temp > LIMITS.MAX_TEMP ? 'border-red-500/50 shadow-[0_0_30px_rgba(239,68,68,0.15)]' : 'border-slate-800/60'}`}>
          <div className="absolute top-6 left-6 flex items-center gap-2 text-xs font-bold tracking-widest uppercase text-slate-500">
            <Thermometer size={14} className={data.temp > LIMITS.MAX_TEMP ? 'text-red-500' : 'text-orange-500'} /> 
            Thermal Core
          </div>
          <div className="text-center">
            <span className={`text-7xl font-black ${data.temp > LIMITS.MAX_TEMP ? 'text-red-500 animate-pulse' : 'text-white'}`}>
              {data.temp.toFixed(1)}<span className="text-3xl text-slate-500 font-light ml-1">°C</span>
            </span>
            <p className="text-xs font-bold uppercase mt-2 text-slate-500 tracking-widest">Core Temperature</p>
          </div>
        </div>

        {/* SYSTEM HEALTH */}
        <div className="lg:col-span-3">
          <div className="h-full bg-slate-900/40 p-6 rounded-[2rem] border border-slate-800/60 flex flex-col">
            <div className="flex justify-between items-center mb-6">
              <span className="text-slate-500 font-bold uppercase text-[10px] tracking-widest">Health Index</span>
              <Activity className="text-emerald-400" size={20} />
            </div>
            <div className="text-6xl font-black text-emerald-400 mb-8">{data.soh.toFixed(1)}<span className="text-lg text-slate-500 font-bold ml-1">%</span></div>
            <div className="mt-auto space-y-3 pt-6 border-t border-slate-800/60">
              <CellHealthMini label="Cell 01" health={data.soh + 0.1} />
              <CellHealthMini label="Cell 02" health={data.soh - 0.2} />
              <CellHealthMini label="Cell 03" health={data.soh} />
            </div>
          </div>
        </div>
      </div>

      {/* CELL LOGISTICS FOOTER */}
      <div className="bg-slate-900/40 rounded-[2rem] border border-slate-800/60 p-8 shadow-2xl">
        <div className="flex justify-between items-end mb-8">
          <div>
            <h3 className="text-slate-400 font-bold uppercase text-xs tracking-widest">Cell Array Logistics</h3>
            <div className="text-3xl font-black text-white mt-1">{totalVoltage.toFixed(2)}V</div>
          </div>
          <div className="px-4 py-2 rounded-xl bg-blue-950/20 border border-blue-900/30 text-blue-400 text-sm font-bold tracking-widest uppercase">
            Load: {Math.abs(data.current).toFixed(2)} A
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <CellRack label="CELL 01" voltage={data.cell1} limits={LIMITS} />
          <CellRack label="CELL 02" voltage={data.cell2} limits={LIMITS} />
          <CellRack label="CELL 03" voltage={data.cell3} limits={LIMITS} />
        </div>
      </div>
    </div>
  );
};

const MetricPanel = ({ title, value, unit, icon, color }) => (
  <div className="bg-slate-900/40 p-6 rounded-[2rem] border border-slate-800/60 flex flex-col justify-between">
    <div className="flex justify-between items-center">
      <span className="text-slate-500 font-bold uppercase text-[10px] tracking-widest">{title}</span>
      <div className={`p-2.5 rounded-xl bg-slate-950/80 border border-slate-800/50 ${color}`}>{icon}</div>
    </div>
    <div className="flex items-baseline gap-1 mt-4">
      <div className={`text-5xl font-black ${color}`}>{value}</div>
      <div className="text-slate-500 font-bold text-lg">{unit}</div>
    </div>
  </div>
);

const CellHealthMini = ({ label, health }) => (
  <div className="flex justify-between items-center bg-slate-950/40 p-3 rounded-xl border border-slate-800/40">
    <span className="text-[11px] text-slate-400 font-bold uppercase tracking-wider">{label}</span>
    <span className="text-xs font-black text-emerald-500">{health.toFixed(1)}%</span>
  </div>
);

const CellRack = ({ label, voltage, limits }) => {
  const isDanger = voltage > limits.MAX_CELL_V || voltage < limits.MIN_CELL_V;
  return (
    <div className={`p-5 rounded-2xl border ${isDanger ? 'bg-red-950/20 border-red-900/50' : 'bg-slate-950/50 border-slate-800/80'}`}>
      <div className="flex justify-between items-center mb-4">
        <span className="text-slate-500 text-xs font-bold uppercase">{label}</span>
        <span className={`font-mono font-black ${isDanger ? 'text-red-400' : 'text-slate-200'}`}>{voltage.toFixed(3)}V</span>
      </div>
      <div className="h-2 bg-slate-900 rounded-full overflow-hidden border border-slate-800">
        <div className={`h-full transition-all duration-700 ${isDanger ? 'bg-red-500' : 'bg-blue-600'}`} style={{ width: `${Math.max(0, Math.min(100, ((voltage - 3.0) / 1.2) * 100))}%` }} />
      </div>
    </div>
  );
};

export default BMSDashboard;