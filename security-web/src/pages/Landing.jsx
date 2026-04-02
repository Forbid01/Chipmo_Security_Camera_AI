/* eslint-disable no-unused-vars */
import '../App.css';
import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { motion, AnimatePresence, useScroll, useSpring } from 'framer-motion';
import { 
  ShieldCheck, Zap, Cpu, Activity, ChevronRight, Lock, Globe, 
  Camera, BrainCircuit, Server, Database, Terminal, GitBranch 
} from 'lucide-react';

import ParticleBackground from './ParticleBackground';

const content = {
  en: {
    nav: { features: "Features", tech: "Technology", contact: "Contact", about: "About", login: "Login" },
    hero: {
      badge: "YOLO11 Neural Engine Active",
      title: "NEXT-GEN",
      subtitle: "RETAIL INTELLIGENCE",
      desc: "Protect your assets with military-grade AI. Our computer vision system monitors your store 24/7, detecting suspicious behavior in real-time.",
      btnInit: "INITIALIZE SYSTEM",
      btnDoc: "Documentation"
    },
    features: {
      tag: "Engineered for Precision",
      desc: "Our architecture combines cutting-edge computer vision with a high-performance backend.",
      f1: { title: "Real-time Detection", desc: "Powered by YOLO11, our models process high-resolution feeds in sub-milliseconds." },
      f2: { title: "Instant Alerts", desc: "Immediate notifications the second suspicious patterns or behaviors are identified." },
      f3: { title: "Deep Analytics", desc: "Comprehensive dashboard for reviewing incident logs and statistical trends." }
    },
    techSection: {
        badge: "System Architecture",
        title1: "THE NEURAL",
        title2: "PIPELINE",
        subtitle: "Built on a modern high-performance stack, our system processes live video feeds through advanced YOLO11 models to detect complex behavioral patterns in real-time.",
        steps: [
          { title: "Video Ingestion", desc: "RTSP/HTTP streams captured from security cameras at 60 FPS." },
          { title: "AI Processing", desc: "YOLO11n-pose evaluates every frame for skeletal anomalies and objects." },
          { title: "Logic Engine", desc: "FastAPI backend calculates intent based on movement history & proximity." },
          { title: "Data & Alerts", desc: "Encrypted storage and instant WebSocket triggers to the React frontend." }
        ],
        techTitle: "Tech Specifications",
        stack: [
          { title: "Frontend Interface", tech: "React 18, Vite, TailwindCSS, Framer Motion" },
          { title: "Backend Microservices", tech: "Python 3.11, FastAPI, WebSocket, OpenCV" },
          { title: "Neural Network", tech: "YOLO11 (Ultralytics), PyTorch, TensorRT" },
          { title: "Database & Storage", tech: "PostgreSQL, SQLAlchemy, Local Artifact Storage" }
        ],
        terminal: {
          load: "Model YOLO11m-pose loaded successfully.",
          conn: "Connecting to Camera_01... [OK]",
          proc: "Processing frames @ 12ms latency...",
          detect: "Subject_ID_84 tracked.",
          alert: "ALERT CRITICAL: Shoplifting behavior identified.",
          trigger: "TRIGGER: WebSocket -> frontend_client",
          save: "SAVE: Writing artifact"
        }
    },
    contact: {
      title: "GET IN TOUCH",
      desc: "If you have questions about the system or partnership proposals, please contact us.",
      form: { name: "Full Name", email: "Email Address", sub: "Subject", msg: "Your Message", send: "SEND MESSAGE", sending: "SENDING..." }
    },
    about: {
      mission: "Our Mission",
      title: "PIONEERING THE FUTURE OF SAFETY",
      desc: "Security.AI aims to solve loss and theft issues in modern retail using AI. We analyze human behavior in real-time using YOLO11.",
      stat1: "Detection Accuracy",
      stat2: "Processing Latency"
    }
  },
  mn: {
    nav: { features: "Боломжууд", tech: "Технологи", contact: "Холбоо барих", about: "Тухай", login: "Нэвтрэх" },
    hero: {
      badge: "YOLO11 Нейрон систем идэвхтэй",
      title: "ШИНЭ ҮЕИЙН",
      subtitle: "УХААЛАГ ХЯНАЛТ",
      desc: "Манай систем таны дэлгүүрийг 24/7 хянаж, сэжигтэй үйлдлийг бодит хугацаанд илрүүлнэ.",
      btnInit: "СИСТЕМИЙГ ЭХЛҮҮЛЭХ",
      btnDoc: "Танилцуулга"
    },
    features: {
      tag: "Нарийвчлалд зориулагдсан",
      desc: "Манай архитектур нь хамгийн сүүлийн үеийн компьютер вишнийг өндөр гүйцэтгэлтэй бэкэндтэй хослуулдаг.",
      f1: { title: "Бодит хугацааны илрүүлэлт", desc: "YOLO11-ээр тоноглогдсон манай модел өндөр нягтралтай дүрсийг миллисекундэд боловсруулдаг." },
      f2: { title: "Шуурхай мэдэгдэл", desc: "Сэжигтэй хөдөлгөөн эсвэл зан төлөв илэрсэн даруйд шууд мэдэгдэл илгээнэ." },
      f3: { title: "Гүнзгий анализ", desc: "Гарсан зөрчлүүд болон долоо хоног, цагийн статистик мэдээллийг хянах боломжтой." }
    },
    techSection: {
        badge: "Системийн бүтэц",
        title1: "НЕЙРОН",
        title2: "ДАМЖУУЛАЛТ",
        subtitle: "Орчин үеийн өндөр гүйцэтгэлтэй технологиуд дээр суурилсан манай систем видео урсгалыг YOLO11 моделиор бодит хугацаанд шинжилж, зан төлөвийн хэв шинжийг илрүүлдэг.",
        steps: [
          { title: "Видео хүлээн авах", desc: "Хяналтын камераас RTSP/HTTP урсгалыг 60 FPS хурдтайгаар хүлээн авна." },
          { title: "AI Боловсруулалт", desc: "YOLO11n-pose ашиглан фрейм бүрт хүний биеийн хөдөлгөөн, объектыг шинжилнэ." },
          { title: "Логик хөдөлгүүр", desc: "FastAPI бэкэнд хөдөлгөөний түүх болон зайн дээр үндэслэн зорилгыг тооцоолно." },
          { title: "Өгөгдөл ба Мэдэгдэл", desc: "Нууцлагдсан хадгалалт болон WebSocket-ээр шуурхай мэдэгдлийг React руу илгээнэ." }
        ],
        techTitle: "Технологийн үзүүлэлт",
        stack: [
          { title: "Фронтенд интерфейс", tech: "React 18, Vite, TailwindCSS, Framer Motion" },
          { title: "Бэкэнд үйлчилгээ", tech: "Python 3.11, FastAPI, WebSocket, OpenCV" },
          { title: "Нейрон сүлжээ", tech: "YOLO11 (Ultralytics), PyTorch, TensorRT" },
          { title: "Өгөгдлийн сан", tech: "PostgreSQL, SQLAlchemy, Local Artifact Storage" }
        ],
        terminal: {
          load: "YOLO11m-pose модел амжилттай ачаалагдлаа.",
          conn: "Camera_01-д холбогдож байна... [OK]",
          proc: "Фрейм боловсруулалт @ 12ms хоцролттой...",
          detect: "Subject_ID_84 илрүүлж, дагаж байна.",
          alert: "ALERT CRITICAL: Хулгайн үйлдэл илэрлээ.",
          trigger: "TRIGGER: WebSocket -> frontend_client руу илгээв",
          save: "SAVE: Видео файлыг хадгалж байна"
        }
    },
    contact: {
      title: "ХОЛБОО БАРИХ",
      desc: "Системийн талаар асуух зүйл болон хамтран ажиллах санал байвал бидэнтэй холбогдоорой. Бид 24 цагийн дотор хариу өгөх болно.",
      form: { name: "Нэр", email: "Имэйл хаяг", sub: "Гарчиг", msg: "Таны зурвас", send: "ЗУРВАС ИЛГЭЭХ", sending: "ИЛГЭЭЖ БАЙНА..." }
    },
    about: {
      mission: "Бидний зорилго",
      title: "АЮУЛГҮЙ БАЙДЛЫН ИРЭЭДҮЙ",
      desc: "Security.AI нь жижиглэн худалдааны салбарт тулгарч буй алдагдал, хулгайн асуудлыг хиймэл оюуны тусламжтай шийдвэрлэх зорилготой.",
      stat1: "Илрүүлэлтийн нарийвчлал",
      stat2: "Боловсруулалтын хурд"
    }
  }
};

const itemVariants = {
    hidden: { opacity: 0, y: 20 },
    visible: { opacity: 1, y: 0, transition: { duration: 0.5 } }
};

export default function Landing() {
  const [lang, setLang] = useState('mn');
  const [showTopBtn, setShowTopBtn] = useState(false);
  const t = content[lang];

  // --- Scroll Progress & Button Visibility ---
  const { scrollYProgress } = useScroll();
  const scaleX = useSpring(scrollYProgress, { stiffness: 100, damping: 30, restDelta: 0.001 });

  useEffect(() => {
    const handleScroll = () => setShowTopBtn(window.scrollY > 500);
    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  // --- Live Accuracy State ---
  const [liveAccuracy, setLiveAccuracy] = useState("99.2");
  useEffect(() => {
    const interval = setInterval(() => {
      const newAcc = (Math.random() * (99.9 - 98.0) + 98.0).toFixed(1);
      setLiveAccuracy(newAcc);
    }, 2000);
    return () => clearInterval(interval);
  }, []);

  // --- Form Logic ---
  const [formData, setFormData] = useState({ name: '', email: '', subject: '', message: '' });
  const [loading, setLoading] = useState(false);

  const handleChange = (e) => setFormData({ ...formData, [e.target.name]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const response = await fetch('http://localhost:8000/api/contact', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData),
      });
      if (response.ok) {
        alert(lang === 'mn' ? "Зурвас амжилттай илгээгдлээ!" : "Message sent successfully!");
        setFormData({ name: '', email: '', subject: '', message: '' });
      } else {
        alert("Error sending message.");
      }
    } catch (error) {
      console.error("Error:", error);
      alert("Could not connect to the server.");
    } finally {
      setLoading(false);
    }
  };

  const scrollToSection = (e, id) => {
    e.preventDefault();
    const element = document.getElementById(id);
    if (element) {
      const offset = 80; 
      const bodyRect = document.body.getBoundingClientRect().top;
      const elementRect = element.getBoundingClientRect().top;
      const elementPosition = elementRect - bodyRect;
      const offsetPosition = elementPosition - offset;
      window.scrollTo({ top: offsetPosition, behavior: 'smooth' });
    }
  };

  const scrollToTop = () => window.scrollTo({ top: 0, behavior: 'smooth' });

  const toggleLang = () => setLang(prev => prev === 'en' ? 'mn' : 'en');

  return (
    <div className="min-h-screen bg-[#05080d] text-slate-200 overflow-x-hidden relative font-sans scroll-smooth">
      <motion.div className="fixed top-0 left-0 right-0 h-1 bg-red-600 origin-left z-[100]" style={{ scaleX }} />

      <ParticleBackground />
      
      {/* Scroll To Top Button */}
      <AnimatePresence>
        {showTopBtn && (
          <motion.button
            initial={{ opacity: 0, scale: 0.5 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.5 }}
            onClick={scrollToTop}
            className="fixed bottom-8 right-8 z-[100] p-4 bg-red-600/90 hover:bg-red-500 text-white rounded-2xl shadow-[0_0_20px_rgba(239,68,68,0.4)] backdrop-blur-md transition-all group"
          >
            <ChevronRight className="-rotate-90 group-hover:-translate-y-1 transition-transform" size={24} />
          </motion.button>
        )}
      </AnimatePresence>

      {/* Navigation */}
      <nav className="fixed top-0 left-0 right-0 z-50 p-6 backdrop-blur-md bg-[#05080d]/60 border-b border-white/5">
        <div className="max-w-[1400px] mx-auto flex justify-between items-center">
          
          {/* Logo Section */}
          <motion.div 
            onClick={scrollToTop}
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            className="flex items-center gap-3 cursor-pointer group relative"
          >
            <div className="relative">
              <div className="absolute inset-0 bg-red-600 blur-xl opacity-0 group-hover:opacity-40 transition-opacity duration-500 rounded-full" />
              <div className="relative p-2.5 bg-gradient-to-br from-slate-900 to-black rounded-xl border border-red-500/30 group-hover:border-red-500/60 transition-all duration-500 shadow-2xl overflow-hidden">
                <ShieldCheck className="text-red-500 group-hover:rotate-[15deg] transition-transform duration-500 relative z-10" size={26} />
                <motion.div animate={{ y: [-20, 40] }} transition={{ duration: 2, repeat: Infinity, ease: "linear" }} className="absolute left-0 w-full h-[1px] bg-red-400/40 shadow-[0_0_8px_red] z-0" />
              </div>
              <div className="absolute -top-1 -right-1 w-2.5 h-2.5 bg-red-600 rounded-full border-2 border-[#05080d] z-20">
                <div className="absolute inset-0 bg-red-500 rounded-full animate-ping" />
              </div>
            </div>
            <div className="flex flex-col justify-center leading-none">
              <h1 className="text-2xl font-black tracking-tighter text-white uppercase italic flex items-center">
                SECURITY<span className="text-red-600 group-hover:text-red-400 transition-colors ml-0.5">.AI</span>
              </h1>
              <span className="text-[7px] font-mono text-slate-500 tracking-[0.3em] uppercase mt-1">Neural Node V11.0</span>
            </div>
          </motion.div>

          <div className="hidden md:flex gap-8 text-[10px] font-bold uppercase tracking-widest text-slate-400">
            {['features', 'tech', 'about', 'contact'].map((item) => (
              <a key={item} href={`#${item}`} onClick={(e) => scrollToSection(e, item)} className="hover:text-white transition-colors">{t.nav[item]}</a>
            ))}
          </div>

          <div className="flex items-center gap-4">
            <button onClick={toggleLang} className="flex items-center gap-2 px-3 py-1.5 rounded-full border border-white/10 bg-white/5 hover:bg-white/10 transition-all text-[10px] font-black font-mono tracking-tighter">
              <Globe size={14} className="text-red-500" />
              {lang === 'en' ? 'MN' : 'ENG'}
            </button>
            <Link to="/login" className="px-6 py-2 bg-white text-black rounded-full font-bold text-xs uppercase hover:scale-105 transition-transform">
              {t.nav.login}
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <main className="relative z-10 max-w-[1400px] mx-auto px-6 pt-48 pb-32 grid lg:grid-cols-2 gap-16 items-center min-h-screen">
        <motion.div initial="hidden" animate="visible" variants={{ visible: { transition: { staggerChildren: 0.1 }}}} className="space-y-8">
          <motion.div variants={itemVariants} className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-red-500/10 border border-red-500/20 text-red-400 text-[10px] font-mono uppercase tracking-widest">
            <Activity size={14} className="animate-pulse" />
            <span>{t.hero.badge}</span>
          </motion.div>
          <motion.h2 variants={itemVariants} className="text-6xl md:text-8xl font-black leading-none tracking-tighter">
            {t.hero.title} <br />
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-red-500 to-orange-500 uppercase">{t.hero.subtitle}</span>
          </motion.h2>
          <motion.p variants={itemVariants} className="text-slate-400 text-lg max-w-xl font-light leading-relaxed">{t.hero.desc}</motion.p>
          <motion.div variants={itemVariants} className="flex flex-wrap gap-4 pt-4">
            <Link to="/login" className="bg-red-600 text-white px-8 py-4 rounded-2xl font-black text-lg hover:shadow-[0_0_30px_rgba(239,68,68,0.3)] transition-all">{t.hero.btnInit}</Link>
            <button className="px-8 py-4 rounded-2xl font-bold text-lg text-slate-300 border border-slate-700 hover:bg-slate-800">{t.hero.btnDoc}</button>
          </motion.div>
        </motion.div>

        <div className="relative group">
          <div className="absolute inset-0 bg-gradient-to-tr from-red-500/20 to-blue-500/20 blur-3xl -z-10" />
          <div className="bg-[#0f172a]/80 backdrop-blur-2xl rounded-[3rem] border border-white/5 overflow-hidden ring-1 ring-white/10 shadow-2xl relative">
            <div className="p-4 border-b border-white/5 bg-slate-900/50 flex items-center gap-2 relative z-20">
              <Activity size={12} className="text-red-500 animate-pulse" />
              <span className="text-[9px] font-mono text-slate-500 uppercase tracking-widest">Cam_01_AI_Neural_Node</span>
            </div>
            <div className="relative h-[400px] overflow-hidden">
              <img src="https://images.unsplash.com/photo-1557597774-9d273605dfa9?q=80&w=1000" className="w-full h-full object-cover opacity-60 grayscale group-hover:grayscale-0 transition-all duration-700" alt="Security" />
              <motion.div animate={{ top: ["0%", "100%", "0%"] }} transition={{ duration: 4, repeat: Infinity, ease: "linear" }} className="absolute left-0 w-full h-[2px] bg-red-500 shadow-[0_0_20px_rgba(239,68,68,0.8)] z-10" />
              <motion.div animate={{ scale: [1, 1.05, 1], opacity: [0.6, 1, 0.6] }} transition={{ repeat: Infinity, duration: 2 }} className="absolute top-[20%] left-[30%] border-2 border-red-500 w-32 h-48 bg-red-500/10 z-10">
                <span className="bg-red-500 text-white text-[8px] px-1 font-mono uppercase animate-pulse">Detected_Pose: 94%</span>
              </motion.div>
            </div>
          </div>
        </div>
      </main>

      {/* Features Section */}
      <section id="features" className="py-32 border-t border-white/5 bg-slate-900/10">
        <div className="max-w-[1400px] mx-auto px-6 text-center">
          <h3 className="text-4xl font-black mb-4 uppercase tracking-tighter">{t.features.tag}</h3>
          <p className="text-slate-400 max-w-2xl mx-auto font-light mb-20">{t.features.desc}</p>
          <div className="grid md:grid-cols-3 gap-8">
            <FeatureCard icon={<ShieldCheck size={32}/>} title={t.features.f1.title} desc={t.features.f1.desc} />
            <FeatureCard icon={<Zap size={32}/>} title={t.features.f2.title} desc={t.features.f2.desc} />
            <FeatureCard icon={<Cpu size={32}/>} title={t.features.f3.title} desc={t.features.f3.desc} />
          </div>
        </div>
      </section>

      {/* Technology Section */}
      <TechnologySection t={t.techSection} />

      {/* About Section */}
      <section id="about" className="py-32 border-t border-white/5">
        <div className="max-w-[1400px] mx-auto px-6 grid lg:grid-cols-2 gap-20 items-center">
          <motion.div initial={{ opacity: 0, x: -30 }} whileInView={{ opacity: 1, x: 0 }} viewport={{ once: true }}>
            <h3 className="text-red-500 font-mono text-sm tracking-[0.3em] uppercase mb-6 underline underline-offset-8">{t.about.mission}</h3>
            <h2 className="text-5xl font-black tracking-tighter mb-8">{t.about.title}</h2>
            <p className="text-slate-400 text-lg font-light leading-relaxed mb-10">{t.about.desc}</p>
            <div className="grid grid-cols-2 gap-6">
              <div><h4 className="text-red-500 font-mono font-bold text-4xl">{liveAccuracy}%</h4><p className="text-slate-500 text-[10px] uppercase font-mono tracking-widest">{t.about.stat1}</p></div>
              <div><h4 className="text-white font-mono font-bold text-4xl">&lt; 12ms</h4><p className="text-slate-500 text-[10px] uppercase font-mono tracking-widest">{t.about.stat2}</p></div>
            </div>
          </motion.div>
          <div className="rounded-[3rem] overflow-hidden border border-white/10 aspect-video grayscale hover:grayscale-0 transition-all duration-1000">
            <img src="https://images.unsplash.com/photo-1550751827-4bd374c3f58b?q=80&w=1000" className="w-full h-full object-cover" alt="AI Core" />
          </div>
        </div>
      </section>

      {/* Contact Section */}
      <section id="contact" className="py-32 bg-slate-900/20 border-t border-white/5">
        <div className="max-w-[1400px] mx-auto px-6">
          <div className="bg-[#0f172a]/60 border border-white/5 rounded-[3.5rem] p-8 md:p-16 grid lg:grid-cols-2 gap-16 relative overflow-hidden">
            <div className="absolute top-0 right-0 w-96 h-96 bg-red-600/10 blur-[100px] pointer-events-none" />
            <div className="relative z-10">
              <h2 className="text-5xl font-black mb-6 tracking-tighter italic">{t.contact.title}</h2>
              <p className="text-slate-400 mb-12 font-light text-lg">{t.contact.desc}</p>
              <div className="space-y-6">
                <ContactInfo icon={<Activity size={20} />} label="Email" value="contact@security.ai" />
                <ContactInfo icon={<ShieldCheck size={20} />} label="Location" value="Ulaanbaatar, Mongolia" />
              </div>
            </div>
            <form onSubmit={handleSubmit} className="space-y-5 relative z-10">
              <div className="grid md:grid-cols-2 gap-5">
                <input type="text" name="name" value={formData.name} onChange={handleChange} required placeholder={t.contact.form.name} className="bg-slate-950/80 border border-white/10 rounded-2xl px-6 py-5 outline-none focus:border-red-500 text-white font-mono text-sm" />
                <input type="email" name="email" value={formData.email} onChange={handleChange} required placeholder={t.contact.form.email} className="bg-slate-950/80 border border-white/10 rounded-2xl px-6 py-5 outline-none focus:border-red-500 text-white font-mono text-sm" />
              </div>
              <input type="text" name="subject" value={formData.subject} onChange={handleChange} required placeholder={t.contact.form.sub} className="w-full bg-slate-950/80 border border-white/10 rounded-2xl px-6 py-5 outline-none focus:border-red-500 text-white font-mono text-sm" />
              <textarea name="message" value={formData.message} onChange={handleChange} required placeholder={t.contact.form.msg} rows="4" className="w-full bg-slate-950/80 border border-white/10 rounded-2xl px-6 py-5 outline-none focus:border-red-500 text-white font-mono text-sm resize-none" />
              <button type="submit" disabled={loading} className="w-full bg-red-600 hover:bg-red-500 text-white font-black py-5 text-sm tracking-widest rounded-2xl transition-all font-mono">
                {loading ? t.contact.form.sending : t.contact.form.send}
              </button>
            </form>
          </div>
        </div>
      </section>

      <footer className="py-12 text-center opacity-40 font-mono text-[9px] uppercase tracking-[0.4em]">
        © 2026 Security.AI - Global Neural Surveillance Network
      </footer>
    </div>
  );
}

function TechnologySection({ t }) {
  const containerVariants = { hidden: { opacity: 0 }, visible: { opacity: 1, transition: { staggerChildren: 0.15 } } };
  return (
    <section id="tech" className="relative z-10 py-24 border-t border-slate-800/50">
      <div className="max-w-[1400px] mx-auto px-6">
        <div className="text-center mb-20">
          <motion.div initial={{ opacity: 0, scale: 0.9 }} whileInView={{ opacity: 1, scale: 1 }} className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-slate-800/50 border border-slate-700 mb-6 uppercase tracking-widest text-xs font-mono">
            <Terminal size={14} className="text-red-400" /> {t.badge}
          </motion.div>
          <h2 className="text-4xl md:text-5xl font-black mb-6 uppercase">
            {t.title1} <span className="text-transparent bg-clip-text bg-gradient-to-r from-red-500 to-amber-500">{t.title2}</span>
          </h2>
          <p className="text-slate-400 max-w-2xl mx-auto text-lg font-light leading-relaxed">{t.subtitle}</p>
        </div>
        <motion.div variants={containerVariants} initial="hidden" whileInView="visible" viewport={{ once: true }} className="grid md:grid-cols-4 gap-6 mb-32 relative">
          <PipelineStep step="01" title={t.steps[0].title} desc={t.steps[0].desc} icon={<Camera size={28} className="text-blue-400" />} glow="bg-blue-500/20" />
          <PipelineStep step="02" title={t.steps[1].title} desc={t.steps[1].desc} icon={<BrainCircuit size={28} className="text-red-400" />} glow="bg-red-500/20" />
          <PipelineStep step="03" title={t.steps[2].title} desc={t.steps[2].desc} icon={<Server size={28} className="text-amber-400" />} glow="bg-amber-500/20" />
          <PipelineStep step="04" title={t.steps[3].title} desc={t.steps[3].desc} icon={<Database size={28} className="text-emerald-400" />} glow="bg-emerald-500/20" />
        </motion.div>
        <div className="grid lg:grid-cols-2 gap-12 items-center">
          <div className="space-y-6">
            <h3 className="text-2xl font-black mb-8 flex items-center gap-3 uppercase font-mono"><GitBranch className="text-red-500" /> {t.techTitle}</h3>
            {t.stack.map((item, idx) => <TechRow key={idx} title={item.title} tech={item.tech} />)}
          </div>
          <div className="bg-[#0b101a]/90 backdrop-blur-sm rounded-2xl border border-slate-800 p-6 font-mono text-sm space-y-2">
            <p><span className="text-green-400">INFO:</span> {t.terminal.load}</p>
            <p><span className="text-blue-400">STREAM:</span> {t.terminal.conn}</p>
            <p className="text-slate-500">{t.terminal.proc}</p>
            <br />
            <p><span className="text-amber-400">DETECT:</span> {t.terminal.detect}</p>
            <p className="text-red-400 font-bold uppercase">{t.terminal.alert}</p>
          </div>
        </div>
      </div>
    </section>
  );
}

function FeatureCard({ icon, title, desc }) {
  return (
    <motion.div whileHover={{ y: -10 }} className="group p-10 rounded-[3.5rem] bg-[#0f172a]/60 border border-white/5 hover:bg-gradient-to-br hover:from-[#151e32] hover:to-red-900/10 transition-all duration-500 overflow-hidden relative">
      <div className="w-16 h-16 rounded-[1.5rem] bg-slate-800/50 border border-white/5 flex items-center justify-center text-slate-400 group-hover:text-red-500 transition-all mb-8">{icon}</div>
      <h4 className="text-2xl font-bold mb-4 text-white uppercase">{title}</h4>
      <p className="text-slate-400 font-light text-sm leading-relaxed">{desc}</p>
    </motion.div>
  );
}

function ContactInfo({ icon, label, value }) {
  return (
    <div className="flex items-center gap-4 group">
      <div className="w-14 h-14 rounded-2xl bg-white/5 border border-white/10 flex items-center justify-center text-red-500 group-hover:bg-red-500/10 transition-all">{icon}</div>
      <div>
        <p className="text-[10px] font-mono text-slate-500 uppercase tracking-widest">{label}</p>
        <p className="text-white font-bold">{value}</p>
      </div>
    </div>
  );
}

function PipelineStep({ step, title, desc, icon, glow }) {
  return (
    <div className="relative p-6 rounded-[2rem] bg-[#0f172a]/80 border border-slate-800 hover:border-slate-600 transition-colors group">
      <div className="absolute top-0 right-6 -translate-y-1/2 text-5xl font-black text-slate-800/30 group-hover:text-red-500/20">{step}</div>
      <div className={`w-14 h-14 rounded-2xl flex items-center justify-center mb-6 relative overflow-hidden bg-slate-900 border border-slate-700`}>
        <div className={`absolute inset-0 opacity-20 ${glow}`} />
        {icon}
      </div>
      <h4 className="text-xl font-bold mb-3 text-white">{title}</h4>
      <p className="text-sm text-slate-400 font-light">{desc}</p>
    </div>
  );
}

function TechRow({ title, tech }) {
  return (
    <div className="p-4 rounded-2xl bg-slate-900/40 border border-slate-800/50 hover:border-red-500/20 transition-all">
      <h4 className="text-sm font-bold text-slate-300 mb-1">{title}</h4>
      <p className="text-red-400/90 font-mono text-sm">{tech}</p>
    </div>
  );
}