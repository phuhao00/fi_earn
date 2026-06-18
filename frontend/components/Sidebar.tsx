"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/", label: "市场总览", icon: "📈" },
  { href: "/market", label: "行情查询", icon: "🔍" },
  { href: "/technical", label: "技术分析", icon: "📊" },
  { href: "/backtest", label: "策略回测", icon: "🚀" },
  { href: "/factor", label: "因子研究", icon: "🔬" },
];

export default function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="w-52 shrink-0 flex flex-col bg-[#1a1d24] border-r border-[#2d3140] h-screen">
      {/* Logo */}
      <div className="px-5 py-5 border-b border-[#2d3140]">
        <div className="text-lg font-bold text-white">fi_earn</div>
        <div className="text-xs text-slate-400 mt-0.5">A股量化研究平台</div>
      </div>

      {/* Nav */}
      <nav className="flex-1 py-4 space-y-1 px-2">
        {NAV.map((item) => {
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors",
                active
                  ? "bg-blue-600/20 text-blue-400 font-medium"
                  : "text-slate-400 hover:bg-[#252a35] hover:text-white"
              )}
            >
              <span>{item.icon}</span>
              <span>{item.label}</span>
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="px-4 py-4 border-t border-[#2d3140] text-xs text-slate-500 space-y-1">
        <div>数据: AkShare（免费）</div>
        <div>回测: AKQuant</div>
        <div>平台: OpenBB</div>
      </div>
    </aside>
  );
}
