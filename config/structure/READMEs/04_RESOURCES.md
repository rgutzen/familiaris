# P.A.Z.R.A.S Resources Guide

> **Purpose**: Reference materials organized by context and format
> **Location**: `~/04_RESOURCES/`
> **Review**: Clean up monthly, archive unused materials quarterly

## Organizing Philosophy: Context + Format

Resources are organized using a **hybrid approach**:

**Context-Based**: *"When and how will I use this?"*
- Templates when creating documents
- Checklists when following procedures
- Reference manuals when troubleshooting

**Format-Based**: *"What type of content is this?"*
- All videos together (easier to browse/search)
- All books together (consistent reading workflow)
- All images together (visual content needs)

This differs from **subject-based** organization (grouping by topic like "Science" or "Technology"). Instead, you organize by the **context of use** and **format type**, making materials easier to find when you actually need them.

**Important distinction**: Resources are passive reference materials you *consult*. For active knowledge development, synthesis, and connected thinking, use the **Zettelkasten** (~/03_ZETTEL/).

## Resources vs Areas vs Zettelkasten Decision Tree

```
New Material → Ask: "Am I responsible for maintaining this?"
├─ YES → 02_AREAS (ongoing responsibility)
└─ NO  → Ask: "Am I developing understanding from this?"
    ├─ YES → 03_ZETTEL (knowledge development)
    └─ NO  → Ask: "Will I reference this across multiple projects/areas?"
        ├─ YES → 04_RESOURCES (cross-cutting reference)
        ├─ NO  → Consider if it belongs in a specific area folder
        └─ OLD → 05_ARCHIVES (no longer useful)
```

## Folder Structure (Context + Format Based)

### Templates/
**Context**: When creating new documents
**Contains**: Reusable formats for emails, presentations, reports, forms, project planning documents, meeting agendas. Organized by type of document rather than subject matter.

### Checklists/
**Context**: When following procedures
**Contains**: Step-by-step guides for research methodology, travel preparation, system setup, quality assurance workflows, or any repeatable process.

### Books/
**Format**: All book content (digital, physical, audiobooks)
**Contains**: Books for reference, learning, or inspiration. Mix completed and to-read books together - organize by title or author, not reading status.

### Videos/
**Format**: All video content
**Contains**: Educational videos, tutorials, conference talks, lectures, interviews, documentaries. Organized by descriptive filenames rather than topic folders.

### Papers/
**Format**: Research papers and academic articles
**Contains**: PDFs of research papers, white papers, academic articles, reports. Use descriptive filenames that include field/topic for easy searching.

### Courses/
**Format**: Structured learning materials
**Contains**: Online course materials, training programs, workshops. Keep all materials from each course together regardless of completion status.

### Pictures/
**Format**: Personal photographs
**Contains**: Personal photos, travel pictures, event photos, family pictures. Visual content that's personal rather than professional.

### Images/
**Format**: Graphics and visual assets
**Contains**: Diagrams, illustrations, logos, icons, infographics, screenshots, visual references for work or projects.

### Audio/
**Format**: Audio files
**Contains**: Podcasts, music, recordings, audio books, sound files, voice memos. All audio content regardless of topic or purpose.

### Tools-Software/
**Context**: When setting up or comparing tools
**Contains**: Software guides, installation instructions, feature comparisons, configuration files, troubleshooting guides, setup documentation.

### Personal-Documents/
**Context**: When needing official documentation
**Contains**: Identity documents, educational certificates, professional certifications, licenses, official personal records that you might need to reference or provide.

### Contracts-Legal/
**Context**: When reviewing agreements or policies
**Contains**: Contract templates, policy documents, legal references, compliance guidelines, agreements, terms of service that you reference.

### Inspiration/
**Context**: When seeking creative ideas
**Contains**: Design examples, writing samples, case studies, creative references, project examples that inspire or guide your work.

### Data-Sources/
**Context**: When conducting analysis or research
**Contains**: Datasets, spreadsheets, API documentation, database access information, data analysis examples, research databases.

### Reference-Manuals/
**Context**: When troubleshooting or learning tools
**Contains**: User guides, technical documentation, software manuals, style guides, specifications, help documents for tools and systems you use.

## What DOESN'T Go in Resources

### Belongs in Areas Instead:
- **Active health records** → `02_AREAS/H_Health/`
- **Current financial plans** → `02_AREAS/N_Finance/`
- **Active travel planning** → `02_AREAS/O_Travel/`
- **Career action items** → `02_AREAS/L_Career/`
- **Current research work** → `02_AREAS/A_Science/` (or relevant area)

### Belongs in Zettelkasten Instead:
- **Concept notes from a book** → `03_ZETTEL/02_Permanent-Notes/`
- **Literature synthesis** → `03_ZETTEL/02_Permanent-Notes/`
- **Connected insights** → `03_ZETTEL/02_Permanent-Notes/`
- **Daily reflections** → `03_ZETTEL/01_Journal/`

### Belongs in Projects Instead:
- **Project-specific research** → `01_PROJECTS/[project-name]/research/`
- **Draft documents** → `01_PROJECTS/[project-name]/drafts/`
- **Active collaboration materials** → `01_PROJECTS/[project-name]/`

## Resource Lifecycle & Workflows

### Adding New Resources
1. **Quick capture** to `00_INBOX/` first
2. **Process during inbox review**: Apply decision tree
3. **File by context of use**, not subject matter
4. **Add descriptive names**: Include status, source, date if relevant

### Example Naming Conventions:
- `Book_BuildingSecondBrain_Forte_2022_Reference.pdf`
- `Template_Email_FollowUp_Professional.md`
- `Checklist_DataAnalysis_Methodology.md`
- `Course_MachineLearning_Stanford_InProgress/`

### Monthly Resource Review (15 minutes)
- **Scan for outdated materials** → Move to archives
- **Check for duplicates** → Keep best version only
- **Review file naming** → Update filenames for better searchability
- **Identify unused resources** → Consider archiving if not referenced in 6+ months

### Cross-Area Resource Strategy
**Problem**: Some resources span multiple areas
**Solution**:
- **Primary location**: Most likely context of use
- **Secondary references**: Create links/shortcuts in relevant areas
- **Tags/notes**: Include area relevance in filename or metadata

## Quick Actions & Navigation

### Navigation Shortcuts
```bash
pr          # Go to resources (here)
```

### Quick Resource Actions
```bash
# Find specific resource type
find ~/04_RESOURCES/ -name "*template*" -type f
find ~/04_RESOURCES/Papers/ -name "*.pdf" | grep -i neuroscience
```

## Common Resource Decisions

| Item Type | → | Location | Rationale |
|-----------|---|----------|-----------|
| Research paper to read | → | `Papers/` | Academic content format |
| Email template | → | `Templates/` | Reusable document format |
| Software tutorial video | → | `Videos/` | Video content format |
| Official transcript | → | `Personal-Documents/` | Official documentation context |
| Investment guide book | → | Link in `N_Finance/` + `Books/` | Area-specific but format-based storage |
| Conference talk video | → | `Videos/` | Video content format |
| Contract template | → | `Contracts-Legal/` | Legal context |
| Design inspiration screenshot | → | `Images/` | Visual content format |
| Data analysis spreadsheet | → | `Data-Sources/` | Analysis context |
| User manual PDF | → | `Reference-Manuals/` | Troubleshooting context |
| Personal photos | → | `Pictures/` | Personal visual content |
| Podcast episode | → | `Audio/` | Audio content format |
| Online course materials | → | `Courses/` | Structured learning format |

## Pro Tips

### Context + Format Organization
- **Ask**: *"When will I need this?"* for context folders (Templates, Checklists)
- **Ask**: *"What format is this?"* for media folders (Books, Videos, Images)
- **Use descriptive filenames**: Include topic, author, date in filename since folders are format-based
- **Example**: `Book_BuildingSecondBrain_Forte_2022.pdf` in Books/ folder

### Avoiding Duplication with Areas and Zettelkasten
- **Resources** = Reference materials for future use across projects
- **Areas** = Active work and ongoing responsibilities
- **Zettelkasten** = Knowledge development and connected thinking
- **When in doubt**: Put in area first, move to resources if it proves useful across multiple projects

### Integration with Zettelkasten
- **Bridge resources to knowledge**: Link resources in permanent notes
- **Resource notes**: Create brief notes about key resources in Zettelkasten
- **Source tracking**: Include resource filename/location in your permanent notes

### Format-Based Benefits
- **Consistent workflows**: All videos use same viewing approach, all books use same reading workflow
- **Easy browsing**: Can scan all videos or all books without jumping between topic folders
- **Search efficiency**: Know exactly where to look based on content type

---

## Review Schedule

- **Weekly**: Quick scan for materials to file from inbox (5 min)
- **Monthly**: Resource cleanup and organization review (15 min)
- **Quarterly**: Archive unused resources, update organization (30 min)

**Remember**: Resources should make your work easier, not create maintenance overhead. If you're not using it, archive it.

---
