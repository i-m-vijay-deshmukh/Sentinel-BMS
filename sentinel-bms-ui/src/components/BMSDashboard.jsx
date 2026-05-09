import React, { useState, useEffect } from 'react';
import { Battery, Zap, Thermometer, Activity, Clock, ShieldAlert, Cpu, PlugZap } from 'lucide-react';
import { PieChart, Pie, Cell, ResponsiveContainer } from 'recharts';

const BMSDashboard = () => {
  const [data, setData] = useState({
    cell1: 0, cell2: 0, cell3: 0, 
    current: 0, temp: 0, 
    charging: false, soh: 100
  });
  const [connectionError, setConnectionError] = useState(null);

  const PACK_CAPACITY_AH = 5.0; 
  const V_MAX_PACK = 12.6;      
  const V_MIN_PACK = 9.0;
  
  const LIMITS = {
    MAX_TEMP: 45.0,        
    MAX_CURRENT: 15.0,     
    MAX_CELL_V: 4.25,      
    MIN_CELL_V: 3.00,      
    MIN_SOH: 80.0          
  };

  useEffect(() => {
    const fetchData = async () => {
      try {
        // Fetches from Render in production, or localhost during development
        const API_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
        const response = await fetch(`${API_URL}/api/react_pull`);
        
        if (!response.ok) throw new Error('Middleware Offline');
        const json = await response.json();
        setData(json);
        setConnectionError(null);
      } catch (err) {
        setConnectionError("Connection Lost: Check Python Server");
      }
    };
    const interval = setInterval(fetchData, 2000);
    return () => clearInterval(interval);
  }, []);

  // --- CALCULATIONS (Blended SOC) ---
  const totalVoltage = data.cell1 + data.cell2 + data.cell3;
  const livePower = totalVoltage * Math.abs(data.current); 
  const avgCellVoltage = totalVoltage / 3.0;
  const minCellVoltage = Math.min(data.cell1, data.cell2, data.cell3);

  let socAvg = ((avgCellVoltage - LIMITS.MIN_CELL_V) / (LIMITS.MAX_CELL_V - LIMITS.MIN_CELL_V)) * 100;
  let socMin = ((minCellVoltage - LIMITS.MIN_CELL_V) / (LIMITS.MAX_CELL_V - LIMITS.MIN_CELL_V)) * 100;

  let soc = (minCellVoltage <= LIMITS.MIN_CELL_V + 0.2) 
    ? socMin 
    : (socMin * 0.70) + (socAvg * 0.30);
  soc = Math.max(0, Math.min(100, soc));

  // --- TIME ESTIMATIONS ---
  const getDischargeTime = () => {
    if (Math.abs(data.current) < 0.05) return "Idle";
    const remainingAh = PACK_CAPACITY_AH * (soc / 100);
    const hours = remainingAh / Math.abs(data.current);
    return `${Math.floor(hours)}h ${Math.round((hours - Math.floor(hours)) * 60)}m`;
  };

  const getChargeTime = () => {
    if (Math.abs(data.current) < 0.05) return "Balancing";
    const missingAh = PACK_CAPACITY_AH - (PACK_CAPACITY_AH * (soc / 100));
    const hours = missingAh / Math.abs(data.current);
    return `${Math.floor(hours)}h ${Math.round((hours - Math.floor(hours)) * 60)}m`;
  };

  // --- GAUGE CHART LOGIC ---
  const TEMP_MAX = 60; 
  const tempValue = Math.min(Math.max(data.temp, 0), TEMP_MAX);
  const gaugeData = [
    { name: 'Temp', value: tempValue },
    { name: 'Empty', value: TEMP_MAX - tempValue }
  ];
  const isTempCritical = data.temp > LIMITS.MAX_TEMP;
  const tempColor = isTempCritical ? '#ef4444' : '#f97316';

  return (
    <div className="min-h-screen bg-[#020617] text-slate-100 p-4 md:p-8 font-sans selection:bg-blue-500/30">
      
      {/* HEADER */}
      <header className="mb-8 flex flex-col md:flex-row justify-between items-start md:items-center gap-4 border-b border-slate-800/60 pb-6">
        <div className="flex items-center gap-4">
          <div className="bg-blue-500/10 p-3 rounded-2xl border border-blue-500/20">
            <Cpu className="text-blue-500" size={28} />
          </div>
          <div>
            <h1 className="text-3xl font-black tracking-tighter text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-indigo-500 drop-shadow-[0_0_15px_rgba(59,130,246,0.2)]">
              SENTINEL-BMS <span className="text-slate-600 font-light text-xl">PRO</span>
            </h1>
            <p className="text-slate-500 text-xs mt-1 uppercase tracking-[0.2em] font-bold">3S 5000mAh EV Architecture</p>
          </div>
        </div>
        
        <div className="flex items-center gap-3">
          {connectionError && (
            <div className="flex items-center gap-2 text-red-400 bg-red-950/40 px-4 py-2 rounded-xl border border-red-900/50 text-sm font-bold shadow-[0_0_15px_rgba(239,68,68,0.2)]">
              <ShieldAlert size={16} /> {connectionError}
            </div>
          )}
          <div className={`px-6 py-2.5 rounded-xl text-sm font-black flex items-center gap-2 border tracking-widest transition-all duration-300 ${data.charging ? 'bg-emerald-900/30 text-emerald-400 border-emerald-500/50 shadow-[0_0_20px_rgba(16,185,129,0.2)] animate-pulse' : 'bg-slate-900/50 text-slate-400 border-slate-700/50'}`}>
            <Zap size={16} fill={data.charging ? "currentColor" : "none"} />
            {data.charging ? "CHARGING" : "DISCHARGING"}
          </div>
        </div>
      </header>

      {/* MAIN COCKPIT LAYOUT */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 mb-6">
        
        {/* LEFT WING: Energy Metrics */}
        <div className="lg:col-span-3 flex flex-col gap-6">
          <MetricPanel title="State of Charge" value={soc.toFixed(1)} unit="%" icon={<Battery />} color="text-blue-400" />
          <MetricPanel title="Live Power" value={livePower.toFixed(1)} unit="W" icon={<Zap />} color="text-yellow-400" alert={Math.abs(data.current) > LIMITS.MAX_CURRENT && !data.charging} />
        </div>

        {/* CENTER CONSOLE: Temperature Gauge */}
        <div className={`lg:col-span-6 relative bg-slate-900/40 backdrop-blur-md rounded-[2rem] border overflow-hidden flex flex-col items-center justify-center p-8 transition-all duration-500 ${isTempCritical ? 'border-red-500/50 shadow-[0_0_30px_rgba(239,68,68,0.15)]' : 'border-slate-800/60 shadow-2xl'}`}>
          <div className="absolute top-6 left-6 flex items-center gap-2 text-xs font-bold tracking-widest uppercase text-slate-500">
            <Thermometer size={14} className={isTempCritical ? 'text-red-500' : 'text-orange-500'} /> 
            Thermal Core
          </div>
          <div className="h-64 w-full mt-8 relative">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={gaugeData} cx="50%" cy="90%" startAngle={180} endAngle={0} innerRadius="75%" outerRadius="100%" paddingAngle={0} dataKey="value" stroke="none" cornerRadius={isTempCritical ? 0 : 5}>
                  <Cell fill={tempColor} className="transition-all duration-500 ease-out" />
                  <Cell fill="#1e293b" /> 
                </Pie>
              </PieChart>
            </ResponsiveContainer>
            <div className="absolute bottom-0 left-0 right-0 flex flex-col items-center justify-end pb-2">
              <span className={`text-6xl font-black tracking-tighter ${isTempCritical ? 'text-red-500 drop-shadow-[0_0_15px_rgba(239,68,68,0.5)] animate-pulse' : 'text-white'}`}>
                {data.temp.toFixed(1)}<span className="text-3xl text-slate-500 font-light ml-1">°C</span>
              </span>
              <span className={`text-xs font-bold tracking-widest uppercase mt-2 ${isTempCritical ? 'text-red-400' : 'text-slate-500'}`}>
                {isTempCritical ? 'CRITICAL OVERHEAT' : 'Nominal Range'}
              </span>
            </div>
          </div>
        </div>

        {/* RIGHT WING: Health & Logistics */}
        <div className="lg:col-span-3 flex flex-col gap-6">
          <MetricPanel 
            title="State of Health" 
            value={data.soh.toFixed(1)} 
            unit="%" 
            icon={<Activity />} 
            color={data.soh <= LIMITS.MIN_SOH ? "text-red-500" : "text-emerald-400"} 
            alert={data.soh <= LIMITS.MIN_SOH} 
          />
          {data.charging ? (
            <MetricPanel title="Time to Full" value={getChargeTime()} unit="" icon={<PlugZap className="text-emerald-400" />} color="text-emerald-400" />
          ) : (
            <MetricPanel title="Est. Range" value={getDischargeTime()} unit="" icon={<Clock />} color="text-slate-200" />
          )}
        </div>
      </div>

      {/* BOTTOM RACK: Cell Array */}
      <div className="bg-slate-900/40 backdrop-blur-md rounded-[2rem] border border-slate-800/60 p-8 shadow-2xl">
        <div className="flex justify-between items-end mb-8">
          <div>
            <h3 className="text-slate-400 font-bold uppercase text-xs tracking-[0.2em]">Cell Array Logistics</h3>
            <div className="text-3xl font-black text-white mt-1">{totalVoltage.toFixed(2)}<span className="text-lg text-slate-500 ml-1">V</span></div>
          </div>
          <div className={`px-4 py-2 rounded-xl border text-sm font-bold tracking-widest uppercase ${Math.abs(data.current) > LIMITS.MAX_CURRENT && !data.charging ? 'bg-orange-950/40 border-orange-500/50 text-orange-400' : 'bg-blue-950/20 border-blue-900/30 text-blue-400'}`}>
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

// --- SUB-COMPONENTS ---
const MetricPanel = ({ title, value, unit, icon, color, alert }) => (
  <div className={`flex-1 bg-slate-900/40 backdrop-blur-md p-6 rounded-[2rem] border ${alert ? 'border-red-500/50 shadow-[0_0_20px_rgba(239,68,68,0.15)]' : 'border-slate-800/60'} flex flex-col justify-between relative overflow-hidden group`}>
    <div className={`absolute -top-10 -right-10 w-32 h-32 blur-3xl opacity-20 rounded-full ${color.replace('text-', 'bg-')} transition-all group-hover:opacity-40`}></div>
    <div className="flex justify-between items-center z-10">
      <span className="text-slate-500 font-bold uppercase text-[10px] tracking-widest">{title}</span>
      <div className={`p-2.5 rounded-xl bg-slate-950/80 border border-slate-800/50 ${color}`}>{icon}</div>
    </div>
    <div className="flex items-baseline gap-1 mt-4 z-10">
      <div className={`text-5xl font-black tracking-tighter ${alert ? 'animate-pulse text-red-500' : color}`}>{value}</div>
      <div className="text-slate-500 font-bold text-lg">{unit}</div>
    </div>
  </div>
);

const CellRack = ({ label, voltage, limits }) => {
  const isDanger = voltage > limits.MAX_CELL_V || voltage < limits.MIN_CELL_V;
  const fillPercentage = Math.max(0, Math.min(100, ((voltage - 3.0) / 1.2) * 100));
  
  return (
    <div className={`p-5 rounded-2xl border ${isDanger ? 'bg-red-950/20 border-red-900/50' : 'bg-slate-950/50 border-slate-800/80'} flex flex-col gap-4`}>
      <div className="flex justify-between items-center">
        <span className="text-slate-500 text-xs font-bold tracking-widest uppercase">{label}</span>
        <span className={`text-xl font-mono font-black ${isDanger ? 'text-red-400' : 'text-slate-200'}`}>{voltage.toFixed(3)}V</span>
      </div>
      <div className="w-full h-3 bg-slate-900 rounded-full overflow-hidden border border-slate-800">
        <div className={`h-full rounded-full transition-all duration-700 ease-out ${isDanger ? 'bg-red-500 shadow-[0_0_10px_rgba(239,68,68,0.8)]' : 'bg-gradient-to-r from-blue-600 to-indigo-400'}`} style={{ width: `${fillPercentage}%` }} />
      </div>
    </div>
  );
};

export default BMSDashboard;