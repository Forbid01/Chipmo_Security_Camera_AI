import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { BarChart3, XCircle } from 'lucide-react';

export const WeeklyChart = ({ data, onBarClick, selectedDay, onClearFilter }) => (
  <div className="bg-[#0f172a]/90 p-6 rounded-[2.5rem] border border-slate-800/50 shadow-xl relative">
    <div className="flex justify-between items-center mb-6">
      <h2 className="flex items-center gap-2 font-semibold text-slate-400 uppercase text-xs tracking-widest font-mono">
        <BarChart3 size={18} className="text-emerald-500" /> Долоо хоногийн зөрчил
      </h2>
      {/* Шүүлтүүрийг арилгах товч */}
      {selectedDay && (
        <button 
          onClick={onClearFilter}
          className="flex items-center gap-1 text-[10px] bg-red-500/10 text-red-500 px-2 py-1 rounded-full border border-red-500/20 hover:bg-red-500/20 transition-all"
        >
          <XCircle size={12} /> {selectedDay} - Арилгах
        </button>
      )}
    </div>
    
    <div className="h-64 w-full">
      <ResponsiveContainer>
        <BarChart data={data}>
          <XAxis dataKey="name" stroke="#475569" fontSize={11} tickLine={false} axisLine={false} />
          <YAxis stroke="#475569" fontSize={11} tickLine={false} axisLine={false} />
          <Tooltip 
            cursor={{fill: '#1e293b', opacity: 0.4}}
            contentStyle={{ backgroundColor: '#0f172a', border: '1px solid #334155', borderRadius: '12px', fontSize: '12px' }}
          />
          <Bar 
            dataKey="count" 
            radius={[6, 6, 0, 0]} 
            onClick={(data) => onBarClick(data.name)}
            style={{ cursor: 'pointer' }}
          >
            {data.map((entry, index) => (
              <Cell 
                key={index} 
                fill={selectedDay === entry.name ? '#10b981' : (entry.count > 5 ? '#ef4444' : '#3b82f6')} 
                fillOpacity={selectedDay && selectedDay !== entry.name ? 0.3 : 0.8} 
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  </div>
);