with open('generate_mix_hud.py', 'r', encoding='utf-8') as f:
    s = f.read()

# 1. Remove old cosmic starfield footer
old_starfield_footer = """    <!-- 5. 科幻星空呼吸底部动态效果 (Sci-Fi Cosmic Starfield Breathing Footer) -->
    <footer class="relative z-10 px-3 py-1 border-t border-cyan-500/25 flex items-center justify-between text-[7px] font-mono-tech shrink-0 overflow-hidden rounded-b-xl" style="height: 30px; background: rgba(8, 10, 16, 0.95); box-shadow: 0 -2px 14px rgba(0, 210, 255, 0.12);">
      <!-- 动态星空画布 -->
      <canvas id="cosmos-canvas" class="absolute inset-0 w-full h-full pointer-events-none z-0"></canvas>
      
      <!-- 浮于星空之上的发光内容 -->
      <div class="relative z-10 flex items-center space-x-1.5 font-luxury tracking-[0.2em] font-medium" style="color: var(--gold-primary); text-shadow: 0 0 8px rgba(223, 186, 115, 0.45);">
        <span class="inline-block w-1.5 h-1.5 rounded-full bg-cyan-400 shadow-[0_0_8px_#00f0ff]" style="animation: pulseGlow 2s infinite ease-in-out;"></span>
        <span class="font-en-luxury font-medium tracking-[0.26em]" style="color: var(--gold-primary);">DESIGN FOR MIX</span>
        <span class="text-cyan-400 opacity-80">✦</span>
      </div>
      
      <div class="relative z-10 flex items-center space-x-1 tracking-[0.16em] uppercase" style="color: var(--text-sub); text-shadow: 0 0 6px rgba(0, 240, 255, 0.3);">
        <span class="text-[6.5px] px-1 py-0.2 rounded border border-cyan-500/30 text-cyan-300 font-mono-tech" style="background: rgba(0, 220, 255, 0.08);">MONOLITH</span>
        <span class="font-mono-tech text-[7px]" style="color: var(--gold-primary);" id="footer-edition-text">R7000</span>
      </div>
    </footer>"""

new_wave_footer = """    <!-- 5. 科技感 3D 波浪网格动态声控底栏 (3D Cyber Wireframe Mesh Wave · Audio Reactive) -->
    <footer class="relative z-10 px-3 py-1 border-t border-purple-500/30 flex items-center justify-between text-[7px] font-mono-tech shrink-0 overflow-hidden rounded-b-xl" style="height: 42px; background: #06050b; box-shadow: 0 -4px 20px rgba(168, 85, 247, 0.18);">
      <!-- 3D 科技感波浪网格动态画布 (随环境音起伏) -->
      <canvas id="wave-mesh-canvas" class="absolute inset-0 w-full h-full pointer-events-none z-0"></canvas>
      
      <!-- 浮于声控网格之上的高级质感铭牌 (DESIGN FOR MIX) -->
      <div class="relative z-10 flex items-center space-x-1.5 font-luxury tracking-[0.26em] font-medium" style="color: #f472b6; text-shadow: 0 0 12px rgba(244, 114, 182, 0.7);">
        <span class="inline-block w-1.5 h-1.5 rounded-full bg-pink-400 shadow-[0_0_8px_#ec4899] animate-pulse"></span>
        <span class="font-en-luxury font-medium tracking-[0.26em]" style="color: #fbcfe8;">DESIGN FOR MIX</span>
        <span class="text-purple-400 opacity-80 text-[6px]">✦</span>
      </div>
      
      <div class="relative z-10 flex items-center space-x-1.5 tracking-[0.16em] uppercase font-mono-tech">
        <!-- 麦克风环境声波联动状态指示 -->
        <div class="flex items-center space-x-1 px-1.5 py-0.5 rounded border border-purple-500/40 text-[6px] text-pink-300 shadow-[0_0_8px_rgba(236,72,153,0.25)]" style="background: rgba(168, 85, 247, 0.15);" id="mic-status-badge">
          <span class="inline-block w-1 h-1 rounded-full bg-pink-400 animate-ping"></span>
          <span>AUDIO RX</span>
        </div>
        <span class="font-mono-tech text-[7px] text-purple-300 font-medium" id="footer-edition-text">MONOLITH R7000</span>
      </div>
    </footer>"""

if old_starfield_footer in s:
    s = s.replace(old_starfield_footer, new_wave_footer)
    print("Footer replaced with 3D wave mesh footer directly!")
else:
    print("Direct footer match failed, using slice...")
    idx = s.find('<!-- 5.')
    end_idx = s.find('</footer>', idx) + 9
    s = s[:idx] + new_wave_footer + s[end_idx:]
    print("Footer replaced via slice!")

# 2. Replace old cosmic starfield JS engine with the 3D Cyber Wireframe Mesh Engine
old_starfield_js_start = "// --- 5. 底部科幻星空呼吸动态引擎"
if old_starfield_js_start in s:
    # Find start and end of starfield JS
    js_idx = s.find(old_starfield_js_start)
    js_end = s.find('</script>', js_idx)
    old_starfield_full = s[js_idx:js_end]
else:
    print("Starfield JS search...")
    old_starfield_full = ""

wave_mesh_js = """// --- 5. 底部科技感 3D 波浪网格动态声控引擎 (3D Cyber Wireframe Mesh Audio-Reactive Engine) ---
    (function initWaveMeshEngine() {
      const canvas = document.getElementById('wave-mesh-canvas');
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      let w = 0, h = 0;

      function resize() {
        const rect = canvas.getBoundingClientRect();
        w = canvas.width = rect.width || window.innerWidth;
        h = canvas.height = rect.height || 42;
      }
      window.addEventListener('resize', resize);
      resize();

      // --- 麦克风环境音量采集与平滑处理 ---
      let audioLevel = 0.15; // 基础环境灵敏度
      let smoothAudio = 0.15;
      let isMicConnected = false;

      function setupMicrophone() {
        if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
          navigator.mediaDevices.getUserMedia({ audio: true, video: false })
            .then(stream => {
              isMicConnected = true;
              const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
              const analyser = audioCtx.createAnalyser();
              const source = audioCtx.createMediaStreamSource(stream);
              source.connect(analyser);
              analyser.fftSize = 64;
              const buffer = new Uint8Array(analyser.frequencyBinCount);

              function pollMic() {
                analyser.getByteFrequencyData(buffer);
                let sum = 0;
                for (let i = 0; i < buffer.length; i++) sum += buffer[i];
                const avg = sum / buffer.length;
                // 灵敏度非线性映射 (0 ~ 1.0)
                audioLevel = Math.min(1.0, Math.pow(avg / 128, 1.2) * 1.5 + 0.1);
                requestAnimationFrame(pollMic);
              }
              pollMic();
            })
            .catch(err => {
              // 未授权或浏览器限制时，使用逼真的有机环境声频节奏自激
              isMicConnected = false;
            });
        }
      }
      setupMicrophone();

      // 点击底栏可主动触发麦克风授权请求
      canvas.parentElement.addEventListener('click', () => {
        if (!isMicConnected) setupMicrophone();
      });

      // 悬浮霓虹微星辉 (Floating Luminous Particles)
      const sparkles = [];
      for (let i = 0; i < 22; i++) {
        sparkles.push({
          x: Math.random(),
          y: Math.random(),
          r: Math.random() * 1.2 + 0.3,
          speed: Math.random() * 0.001 + 0.0005,
          phase: Math.random() * Math.PI * 2
        });
      }

      let time = 0;
      function render() {
        time += 0.025;
        if (!w || !h) resize();

        // 平滑声波响应
        if (!isMicConnected) {
          // 逼真室内环境音仿真模拟：包含键盘敲击脉冲与微弱室内底噪
          const ambientNoise = Math.sin(time * 2.8) * 0.06 + Math.cos(time * 5.1) * 0.04;
          const talkBurst = Math.sin(time * 0.8) > 0.65 ? (Math.sin(time * 12) * 0.25 + 0.25) : 0;
          audioLevel = Math.max(0.12, Math.min(0.85, 0.16 + ambientNoise + talkBurst));
        }
        smoothAudio += (audioLevel - smoothAudio) * 0.12;

        ctx.clearRect(0, 0, w, h);

        // 3D 赛博网格参数
        const cols = 38;      // 横向采样线段
        const rows = 9;       // 纵向深度层切片
        const baseAmp = 3.5 + smoothAudio * 12; // 随声音起伏波幅

        // 预计算 3D 空间网格顶点 (x, y)
        const grid = [];
        for (let r = 0; r < rows; r++) {
          grid[r] = [];
          const depthRatio = r / (rows - 1); // 0.0 (远景山脊) ~ 1.0 (近景波浪)
          const baseY = h * (0.32 + depthRatio * 0.62);

          for (let c = 0; c <= cols; c++) {
            const u = c / cols; // 0.0 ~ 1.0 沿宽度
            // 复合正弦地形波浪：主波 + 次级谐波 + 随声音震颤的高频涟漪
            const wave1 = Math.sin(u * 5.2 + time * 1.8 + depthRatio * 2.4);
            const wave2 = Math.cos(u * 8.6 - time * 2.2 + depthRatio * 1.5) * 0.5;
            const audioRipple = Math.sin(u * 16.0 + time * 6.0) * (smoothAudio * 0.4);
            
            const elevation = (wave1 + wave2 + audioRipple) * baseAmp * (0.35 + depthRatio * 0.65);
            grid[r][c] = {
              x: u * w,
              y: baseY - elevation
            };
          }
        }

        // 1. 绘制横向起伏山脊曲线 (从远到近，带半透明景深暗调遮挡)
        for (let r = 0; r < rows; r++) {
          const depthRatio = r / (rows - 1);
          
          // 纵深渐变色：从远景深紫蓝 -> 近景高亮粉紫霓虹
          const rCol = Math.round(180 + depthRatio * 68);
          const gCol = Math.round(60 + depthRatio * 54);
          const bCol = Math.round(230 + depthRatio * 25);
          const alpha = 0.25 + depthRatio * 0.70;

          // 填充山峦暗影，增强 3D 纵深遮挡感 (如同参考图)
          ctx.beginPath();
          ctx.moveTo(grid[r][0].x, grid[r][0].y);
          for (let c = 1; c <= cols; c++) {
            ctx.lineTo(grid[r][c].x, grid[r][c].y);
          }
          ctx.lineTo(w, h);
          ctx.lineTo(0, h);
          ctx.closePath();
          ctx.fillStyle = `rgba(10, 5, 20, ${0.12 + depthRatio * 0.18})`;
          ctx.fill();

          // 绘制横向主网格线 (带霓虹发光)
          ctx.beginPath();
          ctx.moveTo(grid[r][0].x, grid[r][0].y);
          for (let c = 1; c <= cols; c++) {
            // 平滑贝塞尔曲线连接
            const prev = grid[r][c - 1];
            const curr = grid[r][c];
            const mx = (prev.x + curr.x) / 2;
            const my = (prev.y + curr.y) / 2;
            ctx.quadraticCurveTo(prev.x, prev.y, mx, my);
          }
          ctx.lineTo(grid[r][cols].x, grid[r][cols].y);

          ctx.strokeStyle = `rgba(${rCol}, ${gCol}, ${bCol}, ${alpha})`;
          ctx.lineWidth = 0.75 + depthRatio * 0.65;
          if (r === rows - 1) {
            ctx.shadowColor = 'rgba(244, 114, 182, 0.75)';
            ctx.shadowBlur = 6;
          } else {
            ctx.shadowBlur = 0;
          }
          ctx.stroke();
          ctx.shadowBlur = 0;
        }

        // 2. 绘制纵向透视网格骨骼连线 (Wireframe Ribs)
        ctx.lineWidth = 0.55;
        for (let c = 0; c <= cols; c += 2) {
          ctx.beginPath();
          ctx.moveTo(grid[0][c].x, grid[0][c].y);
          for (let r = 1; r < rows; r++) {
            ctx.lineTo(grid[r][c].x, grid[r][c].y);
          }
          ctx.strokeStyle = `rgba(168, 85, 247, ${0.18 + smoothAudio * 0.25})`;
          ctx.stroke();
        }

        // 3. 悬浮霓虹能量粒子 (漂浮于山峰顶端)
        for (let i = 0; i < sparkles.length; i++) {
          const sp = sparkles[i];
          sp.phase += 0.04;
          sp.y -= sp.speed;
          if (sp.y < 0) sp.y = 1;

          const px = sp.x * w;
          const py = sp.y * (h * 0.75) + 3;
          const pAlpha = (Math.sin(sp.phase) + 1) / 2 * 0.75 + 0.25;

          ctx.beginPath();
          ctx.arc(px, py, sp.r, 0, Math.PI * 2);
          ctx.fillStyle = `rgba(244, 114, 182, ${pAlpha})`;
          ctx.fill();
        }

        requestAnimationFrame(render);
      }
      render();
    })();"""

if old_starfield_full and old_starfield_full in s:
    s = s.replace(old_starfield_full, wave_mesh_js)
    print("Replaced old starfield JS with 3D wave mesh JS!")
else:
    # Append before </script>
    s = s.replace("</script>", wave_mesh_js + "\n  </script>")
    print("Appended 3D wave mesh JS before </script>!")

with open('generate_mix_hud.py', 'w', encoding='utf-8') as f:
    f.write(s)

print("generate_mix_hud.py updated with 3D Wave Mesh and Audio Reactive engine!")
