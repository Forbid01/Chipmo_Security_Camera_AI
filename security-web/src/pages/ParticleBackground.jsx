import { useCallback } from "react";
import Particles from "react-tsparticles";
import { loadSlim } from "tsparticles-slim";

const ParticleBackground = () => {
  const particlesInit = useCallback(async (engine) => {
    await loadSlim(engine);
  }, []);

  return (
    <Particles
      id="tsparticles"
      init={particlesInit}
      className="absolute inset-0 z-0 pointer-events-none"
      options={{
        fullScreen: { enable: false },
        background: { color: "transparent" },
        fpsLimit: 60,
        interactivity: {
          events: {
            onHover: {
              enable: true,
              mode: "grab", // Хулганаар очиход цэгүүд холбогдоно
            },
            resize: true,
          },
          modes: {
            grab: {
              distance: 200,
              links: { opacity: 0.5, color: "#ef4444" }, // Улаан өнгөөр холбогдоно
            },
          },
        },
        particles: {
          color: { value: "#64748b" }, // Үндсэн цэгүүд саарал
          links: {
            color: "#334155",
            distance: 150,
            enable: true,
            opacity: 0.2,
            width: 1,
          },
          move: {
            enable: true,
            speed: 1, // Маш удаан, тайван хөдөлгөөн
            direction: "none",
            outModes: { default: "out" },
          },
          number: {
            density: { enable: true, area: 800 },
            value: 80, // Цэгийн тоо
          },
          opacity: { value: 0.3 },
          shape: { type: "circle" },
          size: { value: { min: 1, max: 3 } },
        },
        detectRetina: true,
      }}
    />
  );
};

export default ParticleBackground;