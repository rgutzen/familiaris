# Zettelkasten - Your Thinking Space

> **Purpose**: Develop and connect ideas, build lasting knowledge
> **Location**: `~/03_ZETTEL/` (also your Obsidian vault)
> **Philosophy**: This is where you THINK, not where you store

## Core Purpose

**Zettelkasten is your knowledge development system**, separate from your work execution system (AREAS) and your reference library (RESOURCES). This is where you:

- **Understand** concepts and ideas
- **Synthesize** information from multiple sources
- **Connect** insights across domains
- **Develop** your thinking over time
- **Build** evergreen knowledge that compounds

Human thinking works through association rather than categories. The Zettelkasten supports this by emphasizing connections between notes over rigid categorization. Area folders within Permanent-Notes provide post-hoc order, but cross-references and tags create the associative web that mirrors how you actually think.

**Zettelkasten vs AREAS vs RESOURCES**:
- **Zettelkasten** = "What does this mean?" (understanding, synthesis)
- **AREAS** = "What am I responsible for?" (doing, executing)
- **RESOURCES** = "Where can I find this?" (referencing, consulting)

## Structure
```
03_ZETTEL/ [Obsidian Vault Root]
├── 00_Inbox/                 # Quick captures, unprocessed notes
├── 01_Journal/               # Daily notes, meeting notes, fleeting thoughts
├── 02_Permanent-Notes/       # Organized knowledge by area
│   ├── A_Science/            # Scientific concepts and methods
│   ├── B_Tech/               # Technology knowledge
│   ├── C_Writing/            # Writing craft
│   ├── D_Art/                # Creative techniques
│   ├── E_Connection/         # Relationship insights
│   ├── F_Community/          # Community building knowledge
│   ├── G_Embodiment/         # Movement understanding
│   ├── H_Health/             # Health knowledge
│   ├── I_Mindfulness/        # Meditation insights
│   ├── J_Culture/            # Cultural/spiritual understanding
│   ├── K_Cuisine/            # Culinary knowledge
│   ├── L_Career/             # Career development insights
│   ├── M_Academia/           # Academic craft knowledge
│   ├── N_Finance/            # Financial understanding
│   ├── O_Travel/             # Travel insights
│   └── P_Home/               # Home management knowledge
├── 03_Maps-Of-Content/       # Topic overviews, structure notes
├── 04_Templates/             # Note templates
└── _assets/                  # Images, PDFs, media for notes
```

## The Zettelkasten Workflow

### 1. **Capture** (00_Inbox)
**When**: Throughout the day as ideas arise
**What**: Quick, unprocessed captures

- Fleeting thoughts
- Quick ideas
- Initial reactions to inputs
- Rough notes from reading

**Duration**: Seconds to capture, don't polish

### 2. **Process** (01_Journal)
**When**: Daily (5-10 minutes)
**What**: Develop fleeting notes into coherent thoughts

- Date-based daily notes (2024-01-08.md)
- Meeting notes with insights
- Talk/conference reflections
- Expanded thoughts from inbox

**Purpose**: Give context and structure before permanence

### 3. **Crystallize** (02_Permanent-Notes)
**When**: Weekly review (15-30 minutes)
**What**: Extract lasting insights into permanent notes

- Single-concept notes
- Well-developed ideas
- Connected to other notes
- Evergreen and timeless

**Key principle**: One idea per note, heavily linked

### 4. **Structure** (03_Maps-Of-Content)
**When**: Monthly or as needed
**What**: Overview notes that connect related permanent notes

- Topic overviews (e.g., "Wave Dynamics in V4")
- Domain maps (e.g., "Scientific Research Methods")
- Project-related knowledge clusters

## What Goes in Each Folder

### 00_Inbox/
**Purpose**: Friction-free capture
**Contains**:
- Quick idea captures
- Rough reading notes
- Initial thoughts on papers
- Unprocessed insights

**Processing**: Daily, move to Journal or delete

### 01_Journal/
**Purpose**: Dated context for developing thoughts
**Contains**:
- Daily notes (YYYY-MM-DD.md format)
- Meeting notes with insights
- Conference/talk reflections
- Expanded inbox items

**Processing**: Weekly, extract insights to Permanent-Notes

### 02_Permanent-Notes/
**Purpose**: Lasting, connected knowledge
**Organization**: By area (matches P.A.Z.R.A.S areas)

**Each area folder contains**:
- Concept notes
- Method understanding
- Theoretical insights
- Literature synthesis

**Note Format**:
```markdown
# Wave Propagation in Cortical Networks

**Tags**: #science #waves #dynamics
**Created**: 2024-01-08
**Area**: A_Science

## Core Concept
Wave-like activity propagates through cortical networks following
specific topological constraints...

## Key Insights
- Propagation speed varies with network density
- Eigenangle analysis reveals temporal structure
- Connection to [[cortical-hierarchy-models]]

## Sources
- [[@Smith2023]] - Original eigenangle paper
- Talk notes: [[2024-01-05-CNS-conference]]

## Related Notes
- [[eigenangle-method]]
- [[network-topology-dynamics]]
- [[temporal-coding-mechanisms]]
```

### 03_Maps-Of-Content/
**Purpose**: Structure and navigate permanent notes
**Contains**:
- Topic overview notes
- Domain maps
- Project-related knowledge clusters

### 04_Templates/
**Purpose**: Consistent note structure
**Contains**: Note templates for different types

## Decision Framework: What Goes Where?

### Zettelkasten vs AREAS vs RESOURCES

| Content Type | Zettelkasten | AREAS | RESOURCES |
|--------------|--------------|-------|-----------|
| **Scientific concept** | Understanding wave dynamics | | |
| **Active experiment** | | Running V4A analysis | |
| **Research method note** | How eigenangle works | | |
| **Current protocol** | | Lab protocol document | |
| **Literature synthesis** | Connecting 3 papers | | |
| **Paper draft** | | Draft in projects | |
| **Paper PDF** | | | Papers/ folder |
| **Meeting insights** | Key learning points | | |
| **Meeting actions** | | Todo items | |
| **Book** | Notes about the book | | Book file in Books/ |

**Golden Rule**:
- **Understanding** → Zettelkasten
- **Execution** → AREAS/PROJECTS
- **Reference material** → RESOURCES

## Common Workflows

### Research Literature Workflow
1. **PDF** → `04_RESOURCES/Papers/`
2. **First read** → Quick notes in `00_Inbox/`
3. **Deep read** → Literature note in `01_Journal/YYYY-MM-DD.md`
4. **Extract concepts** → Permanent notes in `02_Permanent-Notes/[Area]/`
5. **Connect** → Link to related permanent notes
6. **If needed for active work** → Link from `02_AREAS/[Area]/`

### Meeting Note Workflow
1. **During meeting** → Take notes in `01_Journal/YYYY-MM-DD.md`
2. **Mark insights** with `##` or highlight
3. **Mark actions** with `- [ ]` checkboxes
4. **After meeting**:
   - Extract insights → Permanent notes
   - Extract actions → AREAS or project folder
5. **Keep journal entry** as dated record

### Idea Development Workflow
1. **Quick capture** → `00_Inbox/idea-brief-description.md`
2. **Daily review** → Move to `01_Journal/` and expand
3. **Weekly processing** → Create permanent note in relevant area
4. **Link connections** → Connect to existing notes
5. **If actionable** → Create project or task in AREAS

## Best Practices

### Atomic Notes
- **One idea per note** - makes linking powerful
- **Self-contained** - note makes sense on its own
- **Heavily linked** - connect to related ideas

### Evergreen Principle
- Write notes for your **future self**
- Use **present tense** - "This concept works..." not "I learned..."
- Make notes **timeless** - avoid dated references

### Linking Strategy
- Link **concepts**, not just keywords
- Use **context** in link: "This relates to [[wave-dynamics]] through..."
- Create **bidirectional understanding** - why does A connect to B?

## Daily Practice

### Morning (5 min)
- Create today's journal note
- Review yesterday's captures

### During Day (as needed)
- Quick captures to Inbox
- Meeting notes in Journal

### Evening (10 min)
- Process Inbox → Journal
- Expand rough notes
- Mark insights for weekly processing

### Weekly Review (30 min)
- Process Journal → Permanent-Notes
- Create/update Maps of Content
- Review and strengthen connections
- Archive processed journal entries (optional)

## Integration with P.A.Z.R.A.S

### Linking Between Systems
**From Zettelkasten to AREAS**:
```markdown
# Zettelkasten note on eigenangle method

This concept is being applied in:
- [[file:///~/01_PROJECTS/2024-V4A-Analysis/methods.md | V4A Project]]
```

**From AREAS to Zettelkasten**:
```markdown
# AREAS/A_Science/papers-in-progress/wave-paper.md

Theoretical background:
- [[eigenangle-method]]
- [[wave-propagation-theory]]
```

### Natural Flow
```
Input → Zettelkasten/Inbox
     → Process in Journal
     → Crystallize as Permanent-Note
     → (if actionable) Create/Link in AREAS or PROJECTS
```

## Signs of Healthy Zettelkasten

**Good Signs**:
- Notes are connected (not orphans)
- Easy to find related concepts
- Ideas emerge from connections
- You reference old notes frequently
- Inbox processes to zero regularly

**Warning Signs**:
- Inbox growing infinitely
- Notes exist in isolation
- Can't find things when needed
- Notes are just storage, not synthesis
- Duplicating what's in AREAS

## Remember

**Zettelkasten is where you BUILD understanding, not store information.**

- It's a **thinking tool**, not a filing system
- **Quality over quantity** - fewer, better-connected notes
- **Process regularly** - don't let inbox/journal pile up
- **Link generously** - connections create value
- **Write for understanding** - explain concepts in your own words

**The goal**: Build a network of knowledge that helps you think better, not just remember more. And ultimately, to spend more time thinking away from the screen.

---

*Last updated: 2026-02-17*
*System: P.A.Z.R.A.S + Obsidian*
