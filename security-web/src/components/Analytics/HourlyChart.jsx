import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { Clock } from 'lucide-react';

export const HourlyChart = ({ data, selectedHour, onHourClick, onClearHour }) => (
  <div className="bg-[#0f172a]/60 backdrop-blur-xl p-6 rounded-[2.5rem] border border-slate-800/50 shadow-xl relative">
    <div className="flex justify-between items-center mb-6">
      <h2 className="flex items-center gap-2 font-semibold text-slate-400 uppercase text-[10px] tracking-widest font-mono">
        <Clock size={16} className="text-blue-500" /> Hourly Activity
      </h2>
      {selectedHour !== null && (
        <button onClick={onClearHour} className="text-[9px] text-red-500 uppercase font-bold px-2 py-1 bg-red-500/10 rounded-lg">Clear {selectedHour}:00</button>
      )}
    </div>
    <div className="h-48 w-full">
      <ResponsiveContainer>
        <AreaChart data={data} onClick={(e) => e && onHourClick(e.activeLabel)}>
          <defs>
            <linearGradient id="colorBlue" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3}/>
              <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/>
            </linearGradient>
          </defs>
          <XAxis dataKey="name" stroke="#475569" fontSize={9} tickLine={false} axisLine={false} />
          <Tooltip contentStyle={{ backgroundColor: '#0f172a', border: 'none', borderRadius: '12px', fontSize: '10px', color: '#fff' }} />
          <Area 
            type="monotone" 
            dataKey="count" 
            stroke="#3b82f6" 
            strokeWidth={2}
            fill="url(#colorBlue)"
            activeDot={{ r: 6, fill: '#ef4444' }}
            style={{ cursor: 'pointer' }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  </div>
);