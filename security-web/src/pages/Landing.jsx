/* eslint-disable no-unused-vars */
import '../App.css';
import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { motion, AnimatePresence, useScroll, useSpring } from 'framer-motion';
import {
  ShieldCheck, Zap, Cpu, Activity, ChevronRight, Lock, Globe,
  Camera, BrainCircuit, Server, Database, Terminal, GitBranch,
  Phone, Mail, MapPin, Check, Star, Menu, X, MessageSquareQuote,
  ChevronDown, HelpCircle, Store
} from 'lucide-react';

import { sendContactForm } from '../services/api';
import ParticleBackground from './ParticleBackground';

const content = {
  en: {
    nav: { features: "Features", pricing: "Pricing", contact: "Contact", about: "About", login: "Login", register: "Start Free" },
    hero: {
      badge: "AI-Powered Loss Prevention",
      title: "STOP THEFT",
      subtitle: "BEFORE IT HAPPENS",
      desc: "Chipmo turns your existing security cameras into smart theft detectors. Get instant alerts on your phone when suspicious activity is detected — no new hardware needed.",
      btnInit: "START FREE TRIAL",
      btnDoc: "See How It Works"
    },
    features: {
      tag: "Why Store Owners Choose Chipmo",
      desc: "Our customers reduce theft losses by an average of 60%. Here's how.",
      f1: { title: "24/7 Smart Monitoring", desc: "AI watches every camera feed around the clock. No more relying on tired security guards or reviewing hours of footage." },
      f2: { title: "Instant Phone Alerts", desc: "Get a push notification with a snapshot the moment something suspicious happens. React in seconds, not hours." },
      f3: { title: "Weekly Reports", desc: "See which hours are highest risk, which areas need attention, and track how incidents trend over time." }
    },
    techSection: {
        badge: "How It Works",
        title1: "SIMPLE",
        title2: "SETUP",
        subtitle: "Connect your cameras, and Chipmo's AI starts learning your store's patterns within hours. No technical skills required.",
        steps: [
          { title: "Connect Cameras", desc: "Works with any IP camera you already have — RTSP, MJPEG, or USB webcams." },
          { title: "AI Learns Your Store", desc: "Our AI automatically adapts to your store layout, lighting, and traffic patterns." },
          { title: "Real-time Detection", desc: "Suspicious behaviors like concealment, loitering, and grab-and-run are flagged instantly." },
          { title: "You Get Notified", desc: "Alerts with snapshots sent to your dashboard and phone. Review, confirm, or dismiss." }
        ],
        techTitle: "Built for Reliability",
        stack: [
          { title: "Works with any camera", tech: "RTSP, MJPEG, Axis, Hikvision, Dahua, USB" },
          { title: "Cloud or On-premise", tech: "Your data stays where you want it" },
          { title: "Multi-store Support", tech: "Manage all your branches from one dashboard" },
          { title: "Auto-learning AI", tech: "Gets smarter the more you use it — fewer false alarms over time" }
        ],
        terminal: {
          load: "AI model loaded — ready to protect your store.",
          conn: "Camera connected: Front Entrance... [OK]",
          proc: "Monitoring in progress...",
          detect: "Person near high-value shelf tracked.",
          alert: "ALERT: Suspicious concealment behavior detected.",
          trigger: "Notification sent to store manager.",
          save: "Incident snapshot saved."
        }
    },
    pricing: {
      badge: "Per-Camera Pricing",
      title: "TRANSPARENT",
      titleHighlight: "PRICING",
      subtitle: "Platform fee + per-camera rate with volume discounts. The more cameras, the lower the rate.",
      platformFee: "₮29,000",
      platformFeeLabel: "Platform fee / org / month",
      tiers: [
        { range: "1–5 cameras", rate: "₮20,000" },
        { range: "6–20 cameras", rate: "₮17,000" },
        { range: "21–50 cameras", rate: "₮14,000" },
        { range: "51+ cameras", rate: "₮11,000" },
      ],
      tierLabel: "per camera / month",
      plans: [
        {
          name: "Starter",
          price: "₮20,000",
          period: "/camera/mo",
          desc: "1–5 cameras + ₮29,000 platform fee",
          features: ["Up to 5 cameras", "Basic alerts", "7-day history", "Email support"],
          cta: "Start 14-Day Trial",
          highlighted: false
        },
        {
          name: "Business",
          price: "₮17,000",
          period: "/camera/mo",
          desc: "6–20 cameras + ₮29,000 platform fee",
          features: ["Up to 20 cameras", "Instant phone alerts", "30-day history", "Auto-learning AI", "Weekly reports", "Priority support"],
          cta: "Start 14-Day Trial",
          highlighted: true
        },
        {
          name: "Enterprise",
          price: "₮11,000",
          period: "/camera/mo",
          desc: "51+ cameras + ₮29,000 platform fee",
          features: ["Unlimited cameras", "Multi-store dashboard", "On-premise option", "Custom AI training", "Dedicated manager", "SLA guarantee"],
          cta: "Contact Sales",
          highlighted: false
        }
      ]
    },
    contact: {
      title: "LET'S TALK",
      desc: "Questions about setup, pricing, or partnership? We typically respond within 2 hours during business hours.",
      form: { name: "Your Name", email: "Email Address", sub: "Subject", msg: "How can we help?", send: "SEND MESSAGE", sending: "SENDING..." },
      phone: "+976 8810-8766",
      email: "info@chipmo.mn",
      location: "Ulaanbaatar, Mongolia"
    },
    about: {
      mission: "Why We Built This",
      title: "EVERY STORE DESERVES SMART SECURITY",
      desc: "Mongolian retailers lose billions to theft every year. Most can't afford advanced security systems. We built Chipmo to make AI-powered loss prevention accessible to every store — from small shops to large chains.",
      stat1: "Theft Reduction",
      stat2: "Alert Speed"
    },
    testimonials: {
      badge: "Trusted by Store Owners",
      title: "WHAT OUR",
      titleHighlight: "CUSTOMERS SAY",
      items: [
        { name: "Б. Батбаяр", role: "Номин супермаркет, Менежер", text: "Chipmo суулгаснаас хойш бараа алдагдал мэдэгдэхүйц буурсан. Ялангуяа шөнийн ээлжинд AI маш сайн ажиллаж байна." },
        { name: "Д. Оюунчимэг", role: "CU convenience store, Эзэн", text: "Өмнө нь камерын бичлэг шалгахад л цаг үрдэг байсан. Одоо Telegram-аар шууд мэдэгдэл ирдэг болсон нь маш тохиромжтой." },
        { name: "Г. Эрдэнэбат", role: "Techzone electronics, Захирал", text: "3 салбартаа суулгасан. Нэг самбараас бүгдийг хянадаг нь хамгийн давуу тал. AI өөрөө суралцдаг нь гайхалтай." }
      ]
    },
    faq: {
      badge: "FAQ",
      title: "FREQUENTLY",
      titleHighlight: "ASKED QUESTIONS",
      items: [
        { q: "What cameras does Chipmo work with?", a: "Chipmo works with any IP camera — RTSP, MJPEG, Axis, Hikvision, Dahua, and USB webcams. If you already have security cameras, they'll work." },
        { q: "How long does setup take?", a: "About 15 minutes. Connect your cameras, and the AI starts learning your store's patterns within hours." },
        { q: "What if the internet goes down?", a: "Chipmo continues recording locally. Alerts will be sent once connectivity is restored." },
        { q: "How accurate is the detection?", a: "Our AI reduces false alarms over time by learning from your feedback. Most stores see 60%+ theft reduction within the first month." },
        { q: "Is my video data secure?", a: "Yes. All data is encrypted and you can choose cloud or on-premise storage. We never share your data." }
      ]
    }
  },
  mn: {
    nav: { features: "Боломжууд", pricing: "Үнэ", contact: "Холбоо барих", about: "Тухай", login: "Нэвтрэх", register: "Үнэгүй эхлэх" },
    hero: {
      badge: "AI хулгай илрүүлэгч",
      title: "ХУЛГАЙГ",
      subtitle: "УРЬДЧИЛАН СЭРГИЙЛ",
      desc: "Chipmo таны одоо байгаа камеруудыг ухаалаг хулгай илрүүлэгч болгоно. Сэжигтэй үйлдэл илэрмэгц таны утсанд шууд мэдэгдэл ирнэ — нэмэлт төхөөрөмж шаардлагагүй.",
      btnInit: "ҮНЭГҮЙ ТУРШИЖ ҮЗЭХ",
      btnDoc: "Хэрхэн ажилладаг вэ?"
    },
    features: {
      tag: "Дэлгүүрийн эзэд яагаад сонгодог вэ?",
      desc: "Манай харилцагчид хулгайн алдагдлыг дунджаар 60%-иар бууруулсан. Хэрхэн ажилладгийг харна уу.",
      f1: { title: "24/7 Ухаалаг хяналт", desc: "AI таны бүх камерыг шөнө дөлөө хянана. Ядарсан харуул, олон цагийн бичлэг шалгах шаардлагагүй." },
      f2: { title: "Утсанд шууд мэдэгдэл", desc: "Сэжигтэй зүйл илэрмэгц зурагтай мэдэгдэл таны утсанд ирнэ. Цаг биш — секундэд хариу үйлдэл хийнэ." },
      f3: { title: "Долоо хоногийн тайлан", desc: "Аль цагт эрсдэл өндөр, аль хэсэгт анхаарах хэрэгтэй, зөрчил хэрхэн өөрчлөгдөж байгааг хараарай." }
    },
    techSection: {
        badge: "Хэрхэн ажилладаг вэ?",
        title1: "ХЯЛБАР",
        title2: "СУУЛГАЛТ",
        subtitle: "Камераа холбоход л Chipmo-ийн AI таны дэлгүүрийн нөхцөлд хэдэн цагийн дотор суралцаж эхэлнэ. Техникийн мэдлэг шаардлагагүй.",
        steps: [
          { title: "Камер холбох", desc: "Таны одоо байгаа аль ч IP камертай ажиллана — RTSP, MJPEG, USB вэбкам." },
          { title: "AI суралцана", desc: "Манай AI таны дэлгүүрийн зохион байгуулалт, гэрэлтүүлэг, хүний урсгалд автоматаар дасна." },
          { title: "Бодит цагт илрүүлэх", desc: "Бараа нуух, удаан сэлгүүцэх, шүүрэн авах зэрэг сэжигтэй үйлдлийг шууд илрүүлнэ." },
          { title: "Танд мэдэгдэнэ", desc: "Зурагтай мэдэгдэл таны самбар болон утсанд ирнэ. Шалгаж, баталгаажуулж, эсвэл хаана." }
        ],
        techTitle: "Найдвартай систем",
        stack: [
          { title: "Аль ч камертай ажиллана", tech: "RTSP, MJPEG, Axis, Hikvision, Dahua, USB" },
          { title: "Cloud эсвэл дотоод сервер", tech: "Таны мэдээлэл таны хүссэн газар хадгалагдана" },
          { title: "Олон салбар дэмжинэ", tech: "Бүх салбараа нэг самбараас удирдаарай" },
          { title: "Өөрөө суралцдаг AI", tech: "Хэрэглэх тусам илүү оновчтой — худал дохио буурна" }
        ],
        terminal: {
          load: "AI систем ачаалагдлаа — дэлгүүрийг хамгаалахад бэлэн.",
          conn: "Камер холбогдлоо: Үүдний камер... [OK]",
          proc: "Хяналт явагдаж байна...",
          detect: "Үнэтэй барааны тавиур дээр хүн илэрлээ.",
          alert: "АНХААРУУЛГА: Бараа нуух сэжигтэй үйлдэл илэрлээ.",
          trigger: "Мэдэгдэл дэлгүүрийн менежер рүү илгээгдлээ.",
          save: "Зөрчлийн зураг хадгалагдлаа."
        }
    },
    pricing: {
      badge: "Камер тус бүрээр",
      title: "ИЛ ТОД",
      titleHighlight: "ҮНЭЛГЭЭ",
      subtitle: "Платформ хураамж + камерын тоогоор хямдрах үнэ. Камер их байх тусам үнэ буурна.",
      platformFee: "₮29,000",
      platformFeeLabel: "Платформ хураамж / байгууллага / сар",
      tiers: [
        { range: "1–5 камер", rate: "₮20,000" },
        { range: "6–20 камер", rate: "₮17,000" },
        { range: "21–50 камер", rate: "₮14,000" },
        { range: "51+ камер", rate: "₮11,000" },
      ],
      tierLabel: "камер / сар",
      plans: [
        {
          name: "Starter",
          price: "₮20,000",
          period: "/камер/сар",
          desc: "1–5 камер + ₮29,000 платформ хураамж",
          features: ["5 хүртэл камер", "Үндсэн мэдэгдэл", "7 хоногийн түүх", "Имэйл дэмжлэг"],
          cta: "14 хоног туршиж үзэх",
          highlighted: false
        },
        {
          name: "Business",
          price: "₮17,000",
          period: "/камер/сар",
          desc: "6–20 камер + ₮29,000 платформ хураамж",
          features: ["20 хүртэл камер", "Утсанд шууд мэдэгдэл", "30 хоногийн түүх", "Өөрөө суралцдаг AI", "Долоо хоногийн тайлан", "Тэргүүлэх дэмжлэг"],
          cta: "14 хоног туршиж үзэх",
          highlighted: true
        },
        {
          name: "Enterprise",
          price: "₮11,000",
          period: "/камер/сар",
          desc: "51+ камер + ₮29,000 платформ хураамж",
          features: ["Хязгааргүй камер", "Олон салбарын самбар", "Дотоод сервер сонголт", "AI тусгай тохируулга", "Хариуцсан менежер", "SLA баталгаа"],
          cta: "Холбогдох",
          highlighted: false
        }
      ]
    },
    contact: {
      title: "ХОЛБОО БАРИХ",
      desc: "Суулгалт, үнэ, хамтын ажиллагааны талаар асууж болно. Ажлын цагаар 2 цагийн дотор хариу өгнө.",
      form: { name: "Нэр", email: "Имэйл хаяг", sub: "Гарчиг", msg: "Бид яаж тусалж чадах вэ?", send: "ЗУРВАС ИЛГЭЭХ", sending: "ИЛГЭЭЖ БАЙНА..." },
      phone: "+976 8810-8766",
      email: "info@chipmo.mn",
      location: "Улаанбаатар, Монгол"
    },
    about: {
      mission: "Бид яагаад үүнийг бүтээсэн бэ?",
      title: "АЛЬ Ч ДЭЛГҮҮР УХААЛАГ ХАМГААЛАЛТТАЙ БАЙХ ЁСТОЙ",
      desc: "Монголын жижиглэн худалдаачид жил бүр тэрбумаар хулгайд алддаг. Ихэнх нь өндөр үнэтэй хамгаалалтын систем авах боломжгүй. Бид Chipmo-г бүх дэлгүүрт — жижиг лангуунаас том сүлжээ дэлгүүр хүртэл — хүртээмжтэй болгохоор бүтээсэн.",
      stat1: "Хулгай буурсан",
      stat2: "Мэдэгдлийн хурд"
    },
    testimonials: {
      badge: "Харилцагчдын сэтгэгдэл",
      title: "МАНАЙ",
      titleHighlight: "ХАРИЛЦАГЧИД",
      items: [
        { name: "Б. Батбаяр", role: "Номин супермаркет, Менежер", text: "Chipmo суулгаснаас хойш бараа алдагдал мэдэгдэхүйц буурсан. Ялангуяа шөнийн ээлжинд AI маш сайн ажиллаж байна." },
        { name: "Д. Оюунчимэг", role: "CU convenience store, Эзэн", text: "Өмнө нь камерын бичлэг шалгахад л цаг үрдэг байсан. Одоо Telegram-аар шууд мэдэгдэл ирдэг болсон нь маш тохиромжтой." },
        { name: "Г. Эрдэнэбат", role: "Techzone electronics, Захирал", text: "3 салбартаа суулгасан. Нэг самбараас бүгдийг хянадаг нь хамгийн давуу тал. AI өөрөө суралцдаг нь гайхалтай." }
      ]
    },
    faq: {
      badge: "Түгээмэл асуултууд",
      title: "ТҮГЭЭМЭЛ",
      titleHighlight: "АСУУЛТУУД",
      items: [
        { q: "Ямар камертай ажилладаг вэ?", a: "Chipmo аль ч IP камертай ажиллана — RTSP, MJPEG, Axis, Hikvision, Dahua, USB вэбкам. Таны одоо байгаа камерууд ажиллана." },
        { q: "Суулгахад хэр удаан вэ?", a: "Ойролцоогоор 15 минут. Камераа холбоход л AI таны дэлгүүрийн нөхцөлд хэдэн цагийн дотор суралцаж эхэлнэ." },
        { q: "Интернэт унтарвал яах вэ?", a: "Chipmo дотооддоо бичлэг хийсээр байна. Интернэт сэргэмэгц мэдэгдлүүд илгээгдэнэ." },
        { q: "Илрүүлэлт хэр нарийвчлалтай вэ?", a: "Манай AI таны санал хүсэлтээс суралцаж, хуурамч дохиог багасгадаг. Ихэнх дэлгүүр эхний сард хулгайг 60%-иар бууруулсан." },
        { q: "Видео өгөгдөл аюулгүй юу?", a: "Тийм. Бүх мэдээлэл шифрлэгдсэн бөгөөд та cloud эсвэл дотоод сервер сонгож болно. Бид таны мэдээллийг хэзээ ч хуваалцдаггүй." }
      ]
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
  const [mobileMenu, setMobileMenu] = useState(false);
  const t = content[lang];

  // --- Scroll Progress & Button Visibility ---
  const { scrollYProgress } = useScroll();
  const scaleX = useSpring(scrollYProgress, { stiffness: 100, damping: 30, restDelta: 0.001 });

  useEffect(() => {
    const handleScroll = () => setShowTopBtn(window.scrollY > 500);
    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  // --- Form Logic ---
  const [formData, setFormData] = useState({ name: '', email: '', subject: '', message: '' });
  const [loading, setLoading] = useState(false);

  const handleChange = (e) => setFormData({ ...formData, [e.target.name]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await sendContactForm(formData);
      alert(lang === 'mn' ? "Зурвас амжилттай илгээгдлээ!" : "Message sent successfully!");
      setFormData({ name: '', email: '', subject: '', message: '' });
    } catch (error) {
      console.error("Error:", error);
      alert(lang === 'mn' ? "Зурвас илгээхэд алдаа гарлаа." : "Error sending message.");
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
              <h1 className="text-2xl font-black tracking-tighter text-white uppercase flex items-center">
                CHIPMO<span className="text-red-600 group-hover:text-red-400 transition-colors ml-0.5">.AI</span>
              </h1>
              <span className="text-[7px] font-mono text-slate-500 tracking-[0.3em] uppercase mt-1">Smart Loss Prevention</span>
            </div>
          </motion.div>

          <div className="hidden md:flex gap-8 text-[10px] font-bold uppercase tracking-widest text-slate-400">
            {['features', 'pricing', 'about', 'contact'].map((item) => (
              <a key={item} href={`#${item}`} onClick={(e) => scrollToSection(e, item)} className="hover:text-white transition-colors">{t.nav[item]}</a>
            ))}
          </div>

          <div className="hidden md:flex items-center gap-4">
            <button onClick={toggleLang} className="flex items-center gap-2 px-3 py-1.5 rounded-full border border-white/10 bg-white/5 hover:bg-white/10 transition-all text-[10px] font-black font-mono tracking-tighter">
              <Globe size={14} className="text-red-500" />
              {lang === 'en' ? 'MN' : 'ENG'}
            </button>
            <Link to="/login" className="px-5 py-2 border border-slate-600 text-slate-300 rounded-full font-bold text-xs uppercase hover:bg-slate-800 transition-all">
              {t.nav.login}
            </Link>
            <Link to="/register" className="px-5 py-2 bg-red-600 text-white rounded-full font-bold text-xs uppercase hover:bg-red-500 transition-all">
              {t.nav.register}
            </Link>
          </div>

          {/* Mobile hamburger */}
          <button onClick={() => setMobileMenu(!mobileMenu)} className="md:hidden p-2 text-slate-400 hover:text-white">
            {mobileMenu ? <X size={24} /> : <Menu size={24} />}
          </button>
        </div>

        {/* Mobile Menu Dropdown */}
        <AnimatePresence>
          {mobileMenu && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              className="md:hidden overflow-hidden"
            >
              <div className="py-4 px-6 space-y-3 border-t border-white/5">
                {['features', 'pricing', 'about', 'contact'].map((item) => (
                  <a key={item} href={`#${item}`} onClick={(e) => { scrollToSection(e, item); setMobileMenu(false); }}
                     className="block text-sm font-bold uppercase tracking-wider text-slate-400 hover:text-white py-2">{t.nav[item]}</a>
                ))}
                <div className="flex gap-3 pt-3 border-t border-white/10">
                  <button onClick={() => { toggleLang(); setMobileMenu(false); }} className="flex items-center gap-2 px-3 py-2 rounded-full border border-white/10 bg-white/5 text-xs font-bold">
                    <Globe size={14} className="text-red-500" /> {lang === 'en' ? 'MN' : 'ENG'}
                  </button>
                  <Link to="/login" onClick={() => setMobileMenu(false)} className="flex-1 text-center py-2 border border-slate-600 text-slate-300 rounded-full font-bold text-xs uppercase">
                    {t.nav.login}
                  </Link>
                  <Link to="/register" onClick={() => setMobileMenu(false)} className="flex-1 text-center py-2 bg-red-600 text-white rounded-full font-bold text-xs uppercase">
                    {t.nav.register}
                  </Link>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
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
            <Link to="/register" className="bg-red-600 text-white px-8 py-4 rounded-2xl font-black text-lg hover:shadow-[0_0_30px_rgba(239,68,68,0.3)] transition-all">{t.hero.btnInit}</Link>
            <a href="#tech" onClick={(e) => scrollToSection(e, 'tech')} className="px-8 py-4 rounded-2xl font-bold text-lg text-slate-300 border border-slate-700 hover:bg-slate-800 transition-all">{t.hero.btnDoc}</a>
          </motion.div>
        </motion.div>

        <div className="relative group">
          <div className="absolute inset-0 bg-gradient-to-tr from-red-500/20 to-blue-500/20 blur-3xl -z-10" />
          <div className="bg-[#0f172a]/80 backdrop-blur-2xl rounded-[3rem] border border-white/5 overflow-hidden ring-1 ring-white/10 shadow-2xl relative">
            <div className="p-4 border-b border-white/5 bg-slate-900/50 flex items-center justify-between relative z-20">
              <div className="flex items-center gap-2">
                <Activity size={12} className="text-red-500 animate-pulse" />
                <span className="text-[9px] font-mono text-slate-500 uppercase tracking-widest">CAM_01 — Үүдний камер</span>
              </div>
              <span className="text-[8px] font-mono text-slate-600">2026/04/14 15:42:08</span>
            </div>
            <div className="relative h-[400px] overflow-hidden">
              <img src="https://images.unsplash.com/photo-1764083079459-ddb9a615d50e?q=80&w=1000&auto=format&fit=crop" className="w-full h-full object-cover opacity-70 transition-all duration-700" alt="Store monitoring" />
              <motion.div animate={{ top: ["0%", "100%", "0%"] }} transition={{ duration: 4, repeat: Infinity, ease: "linear" }} className="absolute left-0 w-full h-[2px] bg-red-500 shadow-[0_0_20px_rgba(239,68,68,0.8)] z-10" />
              {/* Detection box on person */}
              <motion.div animate={{ scale: [1, 1.03, 1], opacity: [0.7, 1, 0.7] }} transition={{ repeat: Infinity, duration: 2 }} className="absolute top-[15%] left-[35%] border-2 border-red-500 w-28 h-52 bg-red-500/10 z-10">
                <span className="bg-red-600 text-white text-[8px] px-1.5 py-0.5 font-mono uppercase animate-pulse">Сэжигтэй: 87%</span>
                <span className="absolute bottom-0 left-0 bg-black/60 text-amber-400 text-[7px] px-1 py-0.5 font-mono">Бараа нуух</span>
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

      {/* Pricing Section */}
      <PricingSection t={t.pricing} lang={lang} />

      {/* Demo Section */}
      <section id="demo" className="py-32 border-t border-white/5">
        <div className="max-w-[1000px] mx-auto px-6 text-center">
          <motion.div initial={{ opacity: 0, y: 30 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }}>
            <span className="text-red-500 font-mono text-xs tracking-[0.3em] uppercase font-bold">
              {lang === 'mn' ? 'Хэрхэн ажилладгийг харна уу' : 'See It In Action'}
            </span>
            <h2 className="text-5xl font-black tracking-tighter mt-4 mb-6">
              {lang === 'mn' ? 'CHIPMO' : 'CHIPMO'} <span className="text-red-500">{lang === 'mn' ? 'АЖИЛЛАГАА' : 'IN ACTION'}</span>
            </h2>
            <p className="text-slate-400 text-lg font-light mb-12 max-w-xl mx-auto">
              {lang === 'mn'
                ? 'Бодит дэлгүүрт AI хэрхэн сэжигтэй үйлдлийг илрүүлж, мэдэгдэл илгээдгийг харна уу.'
                : 'Watch how Chipmo AI detects suspicious activity in a real store and sends instant alerts.'}
            </p>
          </motion.div>
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            whileInView={{ opacity: 1, scale: 1 }}
            viewport={{ once: true }}
            className="relative aspect-video rounded-[2rem] overflow-hidden border border-white/10 bg-slate-900/60 shadow-2xl"
          >
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-6 bg-gradient-to-br from-slate-900/90 to-[#0f172a]/90">
              <div className="p-5 rounded-full bg-red-500/20 border border-red-500/40">
                <svg className="w-12 h-12 text-red-500" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
              </div>
              <p className="text-slate-400 text-sm font-mono uppercase tracking-widest">
                {lang === 'mn' ? 'Демо видео удахгүй...' : 'Demo video coming soon...'}
              </p>
            </div>
          </motion.div>
        </div>
      </section>

      {/* Testimonials Section */}
      <TestimonialsSection t={t.testimonials} />

      {/* About Section */}
      <section id="about" className="py-32 border-t border-white/5">
        <div className="max-w-[1400px] mx-auto px-6 grid lg:grid-cols-2 gap-20 items-center">
          <motion.div initial={{ opacity: 0, x: -30 }} whileInView={{ opacity: 1, x: 0 }} viewport={{ once: true }}>
            <h3 className="text-red-500 font-mono text-sm tracking-[0.3em] uppercase mb-6 underline underline-offset-8">{t.about.mission}</h3>
            <h2 className="text-5xl font-black tracking-tighter mb-8">{t.about.title}</h2>
            <p className="text-slate-400 text-lg font-light leading-relaxed mb-10">{t.about.desc}</p>
            <div className="grid grid-cols-2 gap-6">
              <div><h4 className="text-red-500 font-mono font-bold text-4xl">~60%</h4><p className="text-slate-500 text-[10px] uppercase font-mono tracking-widest">{t.about.stat1}</p></div>
              <div><h4 className="text-white font-mono font-bold text-4xl">&lt; 3{lang === 'mn' ? ' сек' : 's'}</h4><p className="text-slate-500 text-[10px] uppercase font-mono tracking-widest">{t.about.stat2}</p></div>
            </div>
          </motion.div>
          <div className="rounded-[3rem] overflow-hidden border border-white/10 aspect-video">
            <div className="w-full h-full bg-gradient-to-br from-slate-900 to-[#0f172a] flex flex-col items-center justify-center gap-6 p-10">
              <div className="p-4 bg-red-500/10 rounded-2xl border border-red-500/30">
                <ShieldCheck size={48} className="text-red-500" />
              </div>
              <h3 className="text-2xl font-black text-white uppercase tracking-tight">Chipmo.AI</h3>
              <p className="text-slate-500 text-sm font-mono text-center">Smart Loss Prevention<br/>for Every Store</p>
              <div className="flex gap-4 mt-2">
                <div className="px-3 py-1.5 rounded-lg bg-slate-800/60 border border-slate-700/50 text-[10px] font-mono text-slate-400">AI Detection</div>
                <div className="px-3 py-1.5 rounded-lg bg-slate-800/60 border border-slate-700/50 text-[10px] font-mono text-slate-400">Auto-learning</div>
                <div className="px-3 py-1.5 rounded-lg bg-slate-800/60 border border-slate-700/50 text-[10px] font-mono text-slate-400">Multi-store</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* FAQ Section */}
      <FAQSection t={t.faq} />

      {/* Contact Section */}
      <section id="contact" className="py-32 bg-slate-900/20 border-t border-white/5">
        <div className="max-w-[1400px] mx-auto px-6">
          <div className="bg-[#0f172a]/60 border border-white/5 rounded-[3.5rem] p-8 md:p-16 grid lg:grid-cols-2 gap-16 relative overflow-hidden">
            <div className="absolute top-0 right-0 w-96 h-96 bg-red-600/10 blur-[100px] pointer-events-none" />
            <div className="relative z-10">
              <h2 className="text-5xl font-black mb-6 tracking-tighter italic">{t.contact.title}</h2>
              <p className="text-slate-400 mb-12 font-light text-lg">{t.contact.desc}</p>
              <div className="space-y-6">
                <ContactInfo icon={<Phone size={20} />} label={lang === 'mn' ? "Утас" : "Phone"} value={t.contact.phone} />
                <ContactInfo icon={<Mail size={20} />} label="Email" value={t.contact.email} />
                <ContactInfo icon={<MapPin size={20} />} label={lang === 'mn' ? "Хаяг" : "Location"} value={t.contact.location} />
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

      <footer className="py-12 border-t border-white/5">
        <div className="max-w-[1400px] mx-auto px-6 flex flex-col md:flex-row justify-between items-center gap-4">
          <span className="opacity-40 font-mono text-[9px] uppercase tracking-[0.4em]">© 2026 Chipmo LLC</span>
          <div className="flex gap-6 opacity-40 text-[9px] font-mono uppercase tracking-widest">
            <a href="#features" onClick={(e) => scrollToSection(e, 'features')} className="hover:opacity-100 transition-opacity">{t.nav.features}</a>
            <a href="#pricing" onClick={(e) => scrollToSection(e, 'pricing')} className="hover:opacity-100 transition-opacity">{t.nav.pricing}</a>
            <a href="#contact" onClick={(e) => scrollToSection(e, 'contact')} className="hover:opacity-100 transition-opacity">{t.nav.contact}</a>
          </div>
        </div>
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

function TestimonialsSection({ t }) {
  return (
    <section className="py-32 border-t border-white/5 bg-slate-900/10">
      <div className="max-w-[1400px] mx-auto px-6">
        <div className="text-center mb-20">
          <motion.div initial={{ opacity: 0, scale: 0.9 }} whileInView={{ opacity: 1, scale: 1 }} viewport={{ once: true }} className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-slate-800/50 border border-slate-700 mb-6 uppercase tracking-widest text-xs font-mono">
            <MessageSquareQuote size={14} className="text-emerald-400" /> {t.badge}
          </motion.div>
          <h2 className="text-4xl md:text-5xl font-black mb-6 uppercase tracking-tighter">
            {t.title} <span className="text-transparent bg-clip-text bg-gradient-to-r from-emerald-400 to-cyan-400">{t.titleHighlight}</span>
          </h2>
        </div>
        <div className="grid md:grid-cols-3 gap-8">
          {t.items.map((item, idx) => (
            <motion.div
              key={idx}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: idx * 0.1 }}
              className="p-8 rounded-[2rem] bg-[#0f172a]/60 border border-slate-800/50 hover:border-slate-700 transition-all"
            >
              <div className="flex gap-1 mb-6">
                {[...Array(5)].map((_, i) => (
                  <Star key={i} size={16} className="text-amber-400 fill-amber-400" />
                ))}
              </div>
              <p className="text-slate-300 text-sm leading-relaxed mb-8 font-light">"{item.text}"</p>
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-gradient-to-br from-red-500 to-orange-500 flex items-center justify-center text-white font-black text-sm">
                  {item.name[0]}
                </div>
                <div>
                  <p className="text-sm font-bold text-white">{item.name}</p>
                  <p className="text-[10px] text-slate-500 font-mono">{item.role}</p>
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}

function FAQSection({ t }) {
  const [openIdx, setOpenIdx] = useState(null);
  return (
    <section className="py-32 border-t border-white/5 bg-slate-900/10">
      <div className="max-w-[800px] mx-auto px-6">
        <div className="text-center mb-16">
          <motion.div initial={{ opacity: 0, scale: 0.9 }} whileInView={{ opacity: 1, scale: 1 }} viewport={{ once: true }} className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-slate-800/50 border border-slate-700 mb-6 uppercase tracking-widest text-xs font-mono">
            <HelpCircle size={14} className="text-purple-400" /> {t.badge}
          </motion.div>
          <h2 className="text-4xl md:text-5xl font-black mb-6 uppercase tracking-tighter">
            {t.title} <span className="text-transparent bg-clip-text bg-gradient-to-r from-purple-400 to-pink-400">{t.titleHighlight}</span>
          </h2>
        </div>
        <div className="space-y-4">
          {t.items.map((item, idx) => (
            <motion.div
              key={idx}
              initial={{ opacity: 0, y: 10 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: idx * 0.05 }}
              className="rounded-2xl border border-slate-800/50 bg-[#0f172a]/60 overflow-hidden"
            >
              <button
                onClick={() => setOpenIdx(openIdx === idx ? null : idx)}
                className="w-full px-6 py-5 flex items-center justify-between text-left hover:bg-slate-800/30 transition-all"
              >
                <span className="text-sm font-bold text-white pr-4">{item.q}</span>
                <ChevronDown size={18} className={`text-slate-500 shrink-0 transition-transform ${openIdx === idx ? 'rotate-180' : ''}`} />
              </button>
              <AnimatePresence>
                {openIdx === idx && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.2 }}
                    className="overflow-hidden"
                  >
                    <p className="px-6 pb-5 text-sm text-slate-400 leading-relaxed">{item.a}</p>
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}

function getCameraRate(count) {
  if (count <= 5) return 20000;
  if (count <= 20) return 17000;
  if (count <= 50) return 14000;
  return 11000;
}

function PricingCalculator({ t, lang }) {
  const [cameras, setCameras] = useState(5);
  const rate = getCameraRate(cameras);
  const platformFee = 29000;
  const cameraTotal = cameras * rate;
  const grandTotal = platformFee + cameraTotal;

  const mn = lang === 'mn';

  return (
    <motion.div initial={{ opacity: 0, y: 15 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} className="max-w-3xl mx-auto mb-16">
      <div className="p-6 sm:p-8 rounded-[2rem] bg-[#0f172a]/80 border border-slate-800/60">
        {/* Slider */}
        <div className="mb-6">
          <label className="block text-sm text-slate-400 mb-3 font-mono">
            {mn ? 'Камерын тоо' : 'Number of cameras'}
          </label>
          <div className="flex items-center gap-4">
            <input
              type="range"
              min={1}
              max={100}
              value={cameras}
              onChange={(e) => setCameras(Number(e.target.value))}
              className="flex-1 h-2 rounded-full appearance-none bg-slate-700 accent-red-500 cursor-pointer"
            />
            <div className="min-w-[60px] text-center px-3 py-1.5 rounded-xl bg-slate-800 border border-slate-700">
              <span className="text-xl font-black text-white">{cameras}</span>
            </div>
          </div>
          {/* Tier markers */}
          <div className="flex justify-between mt-2 text-[10px] text-slate-600 font-mono px-1">
            <span>1</span><span>5</span><span>20</span><span>50</span><span>100</span>
          </div>
        </div>

        {/* Tier table */}
        <div className="mb-6">
          <table className="w-full text-sm">
            <tbody>
              {t.tiers.map((tier, i) => {
                const tierRates = [20000, 17000, 14000, 11000];
                const isActive = rate === tierRates[i];
                return (
                  <tr key={i} className={`border-b border-slate-800/50 last:border-0 transition-colors ${isActive ? 'bg-red-600/10' : ''}`}>
                    <td className={`py-2.5 pl-3 pr-6 font-mono ${isActive ? 'text-white' : 'text-slate-500'}`}>
                      {isActive && <span className="inline-block w-1.5 h-1.5 rounded-full bg-red-500 mr-2" />}
                      {tier.range}
                    </td>
                    <td className={`py-2.5 pr-3 text-right font-bold ${isActive ? 'text-white' : 'text-slate-500'}`}>
                      {tier.rate}<span className="font-normal text-xs ml-1 text-slate-600">/{mn ? 'сар' : 'mo'}</span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Calculation breakdown */}
        <div className="space-y-3 pt-4 border-t border-slate-800/50">
          <div className="flex justify-between text-sm">
            <span className="text-slate-400">{mn ? 'Платформ хураамж' : 'Platform fee'}</span>
            <span className="text-slate-300 font-mono">₮{platformFee.toLocaleString()}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-slate-400">{cameras} {mn ? 'камер' : 'cameras'} × ₮{rate.toLocaleString()}</span>
            <span className="text-slate-300 font-mono">₮{cameraTotal.toLocaleString()}</span>
          </div>
          <div className="flex justify-between items-baseline pt-3 border-t border-slate-700/50">
            <span className="text-slate-300 font-bold">{mn ? 'Сарын нийт дүн' : 'Monthly total'}</span>
            <span className="text-2xl sm:text-3xl font-black text-transparent bg-clip-text bg-gradient-to-r from-red-500 to-amber-500">
              ₮{grandTotal.toLocaleString()}
            </span>
          </div>
        </div>
      </div>
    </motion.div>
  );
}

function PricingSection({ t, lang }) {
  return (
    <section id="pricing" className="py-32 border-t border-white/5 bg-slate-900/10">
      <div className="max-w-[1400px] mx-auto px-6">
        <div className="text-center mb-12">
          <motion.div initial={{ opacity: 0, scale: 0.9 }} whileInView={{ opacity: 1, scale: 1 }} viewport={{ once: true }} className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-slate-800/50 border border-slate-700 mb-6 uppercase tracking-widest text-xs font-mono">
            <Star size={14} className="text-amber-400" /> {t.badge}
          </motion.div>
          <h2 className="text-4xl md:text-5xl font-black mb-6 uppercase tracking-tighter">
            {t.title} <span className="text-transparent bg-clip-text bg-gradient-to-r from-red-500 to-amber-500">{t.titleHighlight}</span>
          </h2>
          <p className="text-slate-400 max-w-2xl mx-auto text-lg font-light">{t.subtitle}</p>
        </div>

        {/* Pricing Calculator */}
        <PricingCalculator t={t} lang={lang} />

        <div className="grid md:grid-cols-3 gap-8 max-w-5xl mx-auto">
          {t.plans.map((plan, idx) => (
            <motion.div
              key={idx}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: idx * 0.1 }}
              className={`relative p-8 rounded-[2.5rem] border transition-all ${
                plan.highlighted
                  ? 'bg-gradient-to-b from-red-600/10 to-[#0f172a]/80 border-red-500/40 shadow-[0_0_40px_rgba(239,68,68,0.15)]'
                  : 'bg-[#0f172a]/60 border-slate-800/50 hover:border-slate-700'
              }`}
            >
              {plan.highlighted && (
                <div className="absolute -top-4 left-1/2 -translate-x-1/2 px-4 py-1 bg-red-600 rounded-full text-[10px] font-black uppercase tracking-widest text-white">
                  {lang === 'mn' ? 'Хамгийн түгээмэл' : 'Most Popular'}
                </div>
              )}
              <h3 className="text-lg font-bold text-slate-300 mb-2">{plan.name}</h3>
              <div className="flex items-baseline gap-1 mb-2">
                <span className="text-4xl font-black text-white">{plan.price}</span>
                {plan.period && <span className="text-sm text-slate-500">{plan.period}</span>}
              </div>
              <p className="text-sm text-slate-500 mb-8">{plan.desc}</p>
              <ul className="space-y-3 mb-10">
                {plan.features.map((f, i) => (
                  <li key={i} className="flex items-center gap-3 text-sm text-slate-300">
                    <Check size={16} className={plan.highlighted ? 'text-red-400' : 'text-slate-600'} />
                    {f}
                  </li>
                ))}
              </ul>
              <Link
                to={plan.highlighted ? '/register' : idx === 2 ? '#contact' : '/register'}
                onClick={idx === 2 ? (e) => { e.preventDefault(); document.getElementById('contact')?.scrollIntoView({ behavior: 'smooth' }); } : undefined}
                className={`block text-center w-full py-4 rounded-2xl font-bold text-sm uppercase tracking-wider transition-all ${
                  plan.highlighted
                    ? 'bg-red-600 text-white hover:bg-red-500 shadow-lg'
                    : 'border border-slate-700 text-slate-300 hover:bg-slate-800'
                }`}
              >
                {plan.cta}
              </Link>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}