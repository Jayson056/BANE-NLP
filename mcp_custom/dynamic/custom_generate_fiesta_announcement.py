from mcp_custom.mcp_registry import mcp_custom_tool

@mcp_custom_tool
async def generate_fiesta_announcement(fiesta_name: str, dates: str, location: str, color_scheme: dict, contests: list, mic_letter: str, crown_letter: str) -> str:
    """
    Generates a text-based design concept for a social media announcement.
    """
    announcement_type = "Social Media Announcement (Post/Story size)"
    vibe = "Professional, High-End, Festive"
    main_font = "Bold Sans-Serif (e.g., Anton, Montserrat Bold)"
    accent_font = "Sophisticated Serif (e.g., Playfair Display)"
    
    # Color definitions (conceptual)
    brown_main = color_scheme.get('brown', '#5C4033')
    orange_accent = color_scheme.get('orange', '#FF8C00')
    white_bg = color_scheme.get('white', '#FFFFFF')

    # Design Layout
    layout = [
        f"--- DESIGN CONCEPT: {fiesta_name} ({dates}) ---",
        f"Type: {announcement_type} | Vibe: {vibe}",
        f"Palette: Brown ({brown_main}), Orange ({orange_accent}), White ({white_bg})",
        f"Background: Clean White/Very Light Cream ({white_bg})",
        "",
        "[HEADER]",
        f"  - Text: ADMIRAL FIESTA",
        f"  - Font: {main_font}",
        f"  - Color: {brown_main}",
        "  - Detail: Thin Orange ({orange_accent}) line above and below.",
        "",
        "[YEAR BADGE]",
        "  - Shape: Stylized Anchor/Starburst (conceptually at top-right)",
        f"  - Text: 2026",
        f"  - Color: White ({white_bg}) text on Orange ({orange_accent}) badge.",
        "",
        "[MAIN VISUAL/IMAGE BLOCK]",
        "  - Concept: High-quality photo placeholder or abstract design (organic, elegant shapes in brown/orange).",
        "",
        "[DATES]",
        f"  - Text: {dates} • {location}",
        f"  - Font: {main_font}",
        f"  - Styling: In an orange-bordered banner.",
        "",
        "[CONTESTS & STYLING]",
        "  - Text: [Bold Serif/Decorative Font]",
        f"    • Little Miss Gay",
        f"    • {contests}",
        "",
        "  --- LETTER STYLING REQUEST ---",
        f"  - Letter '{mic_letter.upper()}' (in '{contests}'):",
        "    - Concept: Stylized to incorporate a microphone (conceptual diagram: curve of 'S' forms mic body).",
        f"  - Letter '{crown_letter.upper()}' (in '{contests}'):",
        "    - Concept: The top of the '{crown_letter.lower()}' is stylized into a minimalist crown.",
        "  -----------------------------",
        "",
        "[CALL TO ACTION (CTA)]",
        f"  - Text: REGISTER NOW! / BOOK TICKETS",
        f"  - Styling: Large Brown Button with f{orange_accent} text.",
        "",
        f"[DETAILS PLACEHOLDER]",
        "  - Schedule | Tickets | Special Guests",
        f"  - Font: {accent_font} (for contrast and elegance)",
        "",
        "--- END DESIGN CONCEPT ---"
    ]
    return "\n".join(layout)
