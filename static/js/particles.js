// AXIOM — Animated wave grid (dark mode only)
(function () {
    const canvas = document.createElement('canvas');
    canvas.id = 'axiom-particle-canvas';
    canvas.style.cssText = [
        'position:fixed',
        'top:0',
        'left:0',
        'width:100%',
        'height:100%',
        'pointer-events:none',
        'z-index:0',
    ].join(';');
    document.body.appendChild(canvas);

    const ctx = canvas.getContext('2d');
    let W = 0, H = 0;
    let t = 0;
    let mouse = { x: -9999, y: -9999 };

    // Grid config
    const COLS        = 24;      // vertical lines
    const ROWS        = 16;      // horizontal lines
    const WAVE_AMP    = 18;      // how much nodes shift in px
    const WAVE_SPEED  = 0.0008;  // animation speed
    const MOUSE_R     = 200;     // mouse influence radius in px
    const MOUSE_STR   = 45;      // max px push from mouse
    const LINE_ALPHA  = 0.38;    // base line opacity
    const LINE_WIDTH  = 1.0;

    function resize() {
        W = canvas.width  = window.innerWidth;
        H = canvas.height = window.innerHeight;
    }

    function isDark() {
        return document.documentElement.getAttribute('data-theme') === 'dark';
    }

    // Compute animated position of a grid node
    function nodePos(col, row) {
        const baseX = (col / (COLS - 1)) * W;
        const baseY = (row / (ROWS - 1)) * H;

        // Wave offsets — each node pulses with a unique phase
        const phase = col * 0.55 + row * 0.42;
        const dx = Math.sin(t + phase + row * 0.3) * WAVE_AMP * 0.4;
        const dy = Math.cos(t * 0.85 + phase + col * 0.35) * WAVE_AMP;

        let x = baseX + dx;
        let y = baseY + dy;

        // Mouse repulsion — nodes near cursor get pushed away
        const mdx  = x - mouse.x;
        const mdy  = y - mouse.y;
        const mdist = Math.sqrt(mdx * mdx + mdy * mdy);

        if (mdist < MOUSE_R && mdist > 0) {
            const force = (1 - mdist / MOUSE_R) * MOUSE_STR;
            x += (mdx / mdist) * force;
            y += (mdy / mdist) * force;
        }

        return { x, y };
    }

    function tick() {
        requestAnimationFrame(tick);
        t += WAVE_SPEED * 16; // ~60fps increment

        if (!isDark()) {
            ctx.clearRect(0, 0, W, H);
            return;
        }

        ctx.clearRect(0, 0, W, H);
        ctx.strokeStyle = `rgba(255,255,255,${LINE_ALPHA})`;
        ctx.lineWidth   = LINE_WIDTH;

        // Draw horizontal lines — connect each node to the one to its right
        for (let row = 0; row < ROWS; row++) {
            ctx.beginPath();
            for (let col = 0; col < COLS; col++) {
                const p = nodePos(col, row);
                if (col === 0) ctx.moveTo(p.x, p.y);
                else           ctx.lineTo(p.x, p.y);
            }
            ctx.stroke();
        }

        // Draw vertical lines — connect each node to the one below it
        for (let col = 0; col < COLS; col++) {
            ctx.beginPath();
            for (let row = 0; row < ROWS; row++) {
                const p = nodePos(col, row);
                if (row === 0) ctx.moveTo(p.x, p.y);
                else           ctx.lineTo(p.x, p.y);
            }
            ctx.stroke();
        }
    }

    window.addEventListener('mousemove', e => {
        mouse.x = e.clientX;
        mouse.y = e.clientY;
    }, { passive: true });

    window.addEventListener('mouseleave', () => {
        mouse.x = -9999;
        mouse.y = -9999;
    });

    window.addEventListener('resize', resize);

    resize();
    tick();
})();
