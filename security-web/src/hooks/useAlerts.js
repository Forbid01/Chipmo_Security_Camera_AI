import { useState, useEffect, useMemo } from "react";
import { api } from "../services/api";

export const useAlerts = (refreshInterval = 3000) => {
  const [alerts, setAlerts] = useState([]);

  const fetchAlerts = async () => {
    try {
      const response = await api.get("/alerts");
      const data = response.data?.data || response.data || [];

      if (Array.isArray(data)) {
        setAlerts(data);
      }
    } catch (err) {
      if (err.response?.status === 401) {
        console.error("Auth Error");
      }
    }
  };

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchAlerts();
    const interval = setInterval(fetchAlerts, refreshInterval);
    return () => clearInterval(interval);
  }, [refreshInterval]);

  const chartData = useMemo(() => {
    const days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
    const counts = new Array(7).fill(0);

    alerts.forEach((alert) => {
      let dateStr = alert.event_time || alert.timestamp;

      if (dateStr) {
        const formattedStr =
          typeof dateStr === "string" ? dateStr.replace(" ", "T") : dateStr;
        const date = new Date(formattedStr);

        if (!isNaN(date.getTime())) {
          counts[date.getDay()]++;
        }
      }
    });

    return days.map((day, i) => ({ name: day, count: counts[i] }));
  }, [alerts]);

  return { alerts, chartData, fetchAlerts };
};
