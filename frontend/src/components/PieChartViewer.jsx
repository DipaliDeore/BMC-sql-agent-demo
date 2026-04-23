import React from 'react';
import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer } from 'recharts';

const COLORS = ['#2563eb', '#7c3aed', '#ec4899', '#f59e0b', '#10b981', '#3b82f6', '#8b5cf6', '#f43f5e', '#14b8a6', '#0ea5e9'];

export default function PieChartViewer({ data, config }) {
  if (!data || data.length === 0) return null;
  if (!config || !config.is_pie_chart) return null;

  const { label_column, value_column } = config;

  // Format data for Recharts, handling any data types.
  const chartData = data.map((item) => {
    let rawValue = item[value_column];
    let val = 0;
    if (typeof rawValue === 'number') {
      val = rawValue;
    } else if (typeof rawValue === 'string') {
      val = parseFloat(rawValue.replace(/[^0-9.-]+/g, ""));
    }
    
    let rawLabel = item[label_column];
    let labelText = "Unknown";
    if (rawLabel !== null && rawLabel !== undefined) {
      labelText = String(rawLabel);
    }

    return {
      name: labelText,
      value: isNaN(val) ? 0 : val
    };
  }).filter(item => item.value > 0);

  if (chartData.length === 0) {
    return (
      <div style={{
        padding: '20px', 
        textAlign: 'center', 
        color: 'var(--text-muted)',
        background: 'var(--surface-1)',
        borderRadius: 'var(--radius-md)'
      }}>
        Could not parse numerical values for a pie chart from the column '{value_column}'.
      </div>
    );
  }

  return (
    <div style={{ 
      width: '100%', 
      height: 380, 
      background: 'var(--surface-0)', 
      borderRadius: 'var(--radius-md)',
      padding: '16px',
      boxShadow: 'var(--shadow-sm)',
      border: '1px solid var(--border)',
      marginTop: '12px'
    }}>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={chartData}
            cx="50%"
            cy="50%"
            innerRadius={60}
            outerRadius={100}
            paddingAngle={2}
            dataKey="value"
            animationDuration={800}
            animationEasing="ease-out"
          >
            {chartData.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
            ))}
          </Pie>
          <Tooltip 
            contentStyle={{ 
              borderRadius: '8px', 
              border: 'none',
              boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
              background: 'var(--surface-1)',
              color: 'var(--text)'
            }} 
            itemStyle={{ color: 'var(--text)' }}
          />
          <Legend 
            verticalAlign="bottom" 
            height={36} 
            iconType="circle"
            wrapperStyle={{ paddingTop: '10px', fontSize: '13px', color: 'var(--text)' }}
          />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}
