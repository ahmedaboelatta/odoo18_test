/** @odoo-module **/

async function initHaderSubscriptionExpiryBanner() {
    try {
        const resp = await fetch("/hader/api/v1/subscription/banner-status", {
            method: "GET",
            credentials: "same-origin",
            headers: { Accept: "application/json" },
        });
        if (!resp.ok) {
            return;
        }
        const json = await resp.json();
        const data = json && json.data;
        if (!data || !data.show_banner) {
            return;
        }
        const days = Number(data.days_remaining ?? 0);
        if (days < 0 || days > 15) {
            return;
        }
        if (document.getElementById("hader_subscription_expiry_banner")) {
            return;
        }
        const banner = document.createElement("div");
        banner.id = "hader_subscription_expiry_banner";
        banner.style.cssText = [
            "background-color: #d9edf7",
            "border-bottom: 1px solid #bce8f1",
            "color: #1e3a5f",
            "padding: 12px 40px",
            "text-align: center",
            "position: relative",
            "z-index: 1000",
            "font-size: 14px",
            "line-height: 1.6",
            "width: 100%",
        ].join(";");

        const arText =
            days === 0
                ? "تنبيه: ينتهي اشتراككم في نظام «حاضر» اليوم — يرجى التواصل معنا لتجديد الاشتراك."
                : `باقي على انتهاء اشتراككم في نظام «حاضر» ${days} يوم — يرجى التواصل معنا لتجديد الاشتراك.`;
        const enText =
            days === 0
                ? "Your Hader subscription expires today."
                : `Your Hader subscription expires in ${days} days.`;

        banner.innerHTML = `
            <div style="font-weight: 600;">${arText}</div>
            <div style="font-size: 12.5px; opacity: 0.85;">${enText}</div>
            <button type="button" aria-label="Close" style="position: absolute; top: 10px; right: 16px; background: transparent; border: none; font-size: 20px; line-height: 1; color: #1e3a5f; cursor: pointer; opacity: 0.7;">&times;</button>
        `;
        const closeBtn = banner.querySelector("button");
        if (closeBtn) {
            closeBtn.addEventListener("click", () => banner.remove());
        }

        const mountBanner = () => {
            if (document.getElementById("hader_subscription_expiry_banner")) {
                return true;
            }
            const navbar = document.querySelector(".o_main_navbar");
            if (navbar && navbar.parentNode) {
                navbar.parentNode.insertBefore(banner, navbar.nextSibling);
                return true;
            }
            const webClient = document.querySelector(".o_web_client");
            if (webClient) {
                webClient.prepend(banner);
                return true;
            }
            return false;
        };

        if (!mountBanner()) {
            let attempts = 0;
            const timer = setInterval(() => {
                attempts += 1;
                if (mountBanner() || attempts > 20) {
                    clearInterval(timer);
                }
            }, 500);
        }
    } catch (_e) {
        // Ignore banner fetch errors silently
    }
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
        setTimeout(initHaderSubscriptionExpiryBanner, 800);
    });
} else {
    setTimeout(initHaderSubscriptionExpiryBanner, 800);
}
