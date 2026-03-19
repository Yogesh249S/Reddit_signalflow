DELETE FROM subreddit_config;

INSERT INTO subreddit_config (name, interval_seconds, priority, is_active) VALUES

-- ══════════════════════════════════════════════════════════════════
-- FAST TIER (60s) — Highest velocity, breaks first on Reddit
-- Massive subscriber bases, hundreds of posts per hour
-- ══════════════════════════════════════════════════════════════════

-- Humor & Viral
('funny',                  60, 'fast', true),
('memes',                  60, 'fast', true),
('dankmemes',              60, 'fast', true),
('cursedcomments',         60, 'fast', true),
('nextfuckinglevel',       60, 'fast', true),
('interestingasfuck',      60, 'fast', true),

-- Q&A & Discussion
('AskReddit',              60, 'fast', true),
('OutOfTheLoop',           60, 'fast', true),
('NoStupidQuestions',      60, 'fast', true),
('explainlikeimfive',      60, 'fast', true),
('Showerthoughts',         60, 'fast', true),
('changemyview',           60, 'fast', true),
('AmItheAsshole',          60, 'fast', true),
('relationship_advice',    60, 'fast', true),
('tifu',                   60, 'fast', true),
('confession',             60, 'fast', true),

-- News & World Events
('worldnews',              60, 'fast', true),
('news',                   60, 'fast', true),
('politics',               60, 'fast', true),
('todayilearned',          60, 'fast', true),
('nottheonion',            60, 'fast', true),
('UpliftingNews',          60, 'fast', true),

-- Gaming (event-driven, live threads)
('gaming',                 60, 'fast', true),
('pcgaming',               60, 'fast', true),
('GameDeals',              60, 'fast', true),
('ps5',                    60, 'fast', true),
('XboxSeriesX',            60, 'fast', true),

-- Finance (moves in minutes)
('wallstreetbets',         60, 'fast', true),
('IndianStreetBets',       60, 'fast', true),

-- Sports (live game threads = real-time flood)
('nba',                    60, 'fast', true),
('nfl',                    60, 'fast', true),
('soccer',                 60, 'fast', true),
('formula1',               60, 'fast', true),

-- Anime (insane post velocity)
('anime',                  60, 'fast', true),

-- ══════════════════════════════════════════════════════════════════
-- MEDIUM TIER (180s) — High engagement, focused communities
-- Strong comment-to-post ratios, reliable NLP signal
-- ══════════════════════════════════════════════════════════════════

-- AI / Tech
('technology',            180, 'medium', true),
('artificial',            180, 'medium', true),
('ChatGPT',               180, 'medium', true),
('LocalLLaMA',            180, 'medium', true),
('OpenAI',                180, 'medium', true),
('singularity',           180, 'medium', true),
('MachineLearning',       180, 'medium', true),
('programming',           180, 'medium', true),
('learnprogramming',      180, 'medium', true),
('Python',                180, 'medium', true),
('javascript',            180, 'medium', true),
('webdev',                180, 'medium', true),
('linux',                 180, 'medium', true),
('cybersecurity',         180, 'medium', true),
('cscareerquestions',     180, 'medium', true),
('leetcode',              180, 'medium', true),
('StableDiffusion',       180, 'medium', true),

-- Finance
('stocks',                180, 'medium', true),
('investing',             180, 'medium', true),
('personalfinance',       180, 'medium', true),
('CryptoCurrency',        180, 'medium', true),
('Bitcoin',               180, 'medium', true),
('Superstonk',            180, 'medium', true),
('financialindependence', 180, 'medium', true),
('IndiaInvestments',      180, 'medium', true),

-- Sports
('baseball',              180, 'medium', true),
('hockey',                180, 'medium', true),
('tennis',                180, 'medium', true),
('cricket',               180, 'medium', true),
('MMA',                   180, 'medium', true),
('boxing',                180, 'medium', true),
('CollegeBasketball',     180, 'medium', true),

-- Entertainment & Pop Culture
('movies',                180, 'medium', true),
('television',            180, 'medium', true),
('marvelstudios',         180, 'medium', true),
('StarWars',              180, 'medium', true),
('music',                 180, 'medium', true),
('hiphopheads',           180, 'medium', true),
('popheads',              180, 'medium', true),
('books',                 180, 'medium', true),
('boxoffice',             180, 'medium', true),
('flicks',                180, 'medium', true),

-- Gossip & Celebrity
('Fauxmoi',               180, 'medium', true),
('Deuxmoi',               180, 'medium', true),
('popculturechat',        180, 'medium', true),
('celebrities',           180, 'medium', true),
('BravoRealHousewives',   180, 'medium', true),
('rupaulsdragrace',       180, 'medium', true),
('KUWTK',                 180, 'medium', true),
('realtv',                180, 'medium', true),
('survivor',              180, 'medium', true),

-- Indian Film & Gossip
('bollywood',             180, 'medium', true),
('BollywoodMemes',        180, 'medium', true),
('BollywoodGossip',       180, 'medium', true),
('DesiCeleb',             180, 'medium', true),
('tollywood',             180, 'medium', true),
('kollywood',             180, 'medium', true),
('MalayalamMovies',       180, 'medium', true),
('IndianCinema',          180, 'medium', true),
('entertainment',         180, 'medium', true),

-- India General
('india',                 180, 'medium', true),
('indiasocial',           180, 'medium', true),
('bangalore',             180, 'medium', true),
('mumbai',                180, 'medium', true),
('delhi',                 180, 'medium', true),
('IndiaSpeaks',           180, 'medium', true),
('librandu',              180, 'medium', true),

-- Lifestyle
('AskMen',                180, 'medium', true),
('AskWomen',              180, 'medium', true),
('loseit',                180, 'medium', true),
('fitness',               180, 'medium', true),
('cooking',               180, 'medium', true),
('food',                  180, 'medium', true),
('DIY',                   180, 'medium', true),
('LifeAdvice',            180, 'medium', true),
('dating_advice',         180, 'medium', true),

-- Gaming Medium
('gamedev',               180, 'medium', true),
('indiegaming',           180, 'medium', true),
('rpg',                   180, 'medium', true),
('leagueoflegends',       180, 'medium', true),
('GlobalOffensive',       180, 'medium', true),
('Minecraft',             180, 'medium', true),

-- ══════════════════════════════════════════════════════════════════
-- SLOW TIER (600s) — Niche but deeply engaged
-- Highest comment-to-upvote ratios = richest NLP signal
-- Users spending 2x site average time per post
-- ══════════════════════════════════════════════════════════════════

-- Deep Tech
('rust',                  600, 'slow', true),
('golang',                600, 'slow', true),
('devops',                600, 'slow', true),
('aws',                   600, 'slow', true),
('kubernetes',            600, 'slow', true),
('selfhosted',            600, 'slow', true),
('homelab',               600, 'slow', true),
('netsec',                600, 'slow', true),
('ReverseEngineering',    600, 'slow', true),
('datascience',           600, 'slow', true),
('compsci',               600, 'slow', true),
('SoftwareEngineering',   600, 'slow', true),
('ExperiencedDevs',       600, 'slow', true),
('haskell',               600, 'slow', true),
('cpp',                   600, 'slow', true),

-- Science & Academia
('science',               600, 'slow', true),
('physics',               600, 'slow', true),
('math',                  600, 'slow', true),
('neuroscience',          600, 'slow', true),
('chemistry',             600, 'slow', true),
('space',                 600, 'slow', true),
('Astronomy',             600, 'slow', true),
('biology',               600, 'slow', true),
('medicine',              600, 'slow', true),
('AskScience',            600, 'slow', true),
('Futurology',            600, 'slow', true),
('longevity',             600, 'slow', true),
('nutrition',             600, 'slow', true),

-- Finance Deep Cuts
('algotrading',           600, 'slow', true),
('SecurityAnalysis',      600, 'slow', true),
('ValueInvesting',        600, 'slow', true),
('Bogleheads',            600, 'slow', true),
('quant',                 600, 'slow', true),
('economics',             600, 'slow', true),

-- Ideas / Society
('geopolitics',           600, 'slow', true),
('history',               600, 'slow', true),
('philosophy',            600, 'slow', true),
('TrueReddit',            600, 'slow', true),
('slatestarcodex',        600, 'slow', true),
('law',                   600, 'slow', true),
('legaladvice',           600, 'slow', true),
('skeptic',               600, 'slow', true),
('worldpolitics',         600, 'slow', true),

-- Mental Health (deep comment signal, strong sentiment)
('mentalhealth',          600, 'slow', true),
('depression',            600, 'slow', true),
('anxiety',               600, 'slow', true),
('offmychest',            600, 'slow', true),
('SuicideWatch',          600, 'slow', true),

-- Hobbies with 2x avg time-on-page
('boardgames',            600, 'slow', true),
('photography',           600, 'slow', true),
('MechanicalKeyboards',   600, 'slow', true),
('running',               600, 'slow', true),
('climbing',              600, 'slow', true),
('solotravel',            600, 'slow', true),
('travel',                600, 'slow', true),
('vandwellers',           600, 'slow', true),
('minimalism',            600, 'slow', true),
('ZeroWaste',             600, 'slow', true),

-- Niche Entertainment
('criterion',             600, 'slow', true),
('TrueFilm',              600, 'slow', true),
('horror',                600, 'slow', true),
('scifi',                 600, 'slow', true),
('fantasy',               600, 'slow', true),
('comicbooks',            600, 'slow', true),
('DCcomics',              600, 'slow', true),
('HarryPotter',           600, 'slow', true),
('gameofthrones',         600, 'slow', true),
('breakingbad',           600, 'slow', true),

-- Career & Self Improvement
('jobs',                  600, 'slow', true),
('careerguidance',        600, 'slow', true),
('productivity',          600, 'slow', true),
('GetMotivated',          600, 'slow', true),
('selfimprovement',       600, 'slow', true),
('digitalnomad',          600, 'slow', true),

-- Indian Slow
('IndiaTech',             600, 'slow', true),
('developersIndia',       600, 'slow', true),
('CAIndia',               600, 'slow', true),
('UPSC',                  600, 'slow', true)

-- Additional reach
--('mildlyinteresting',     180, 'medium', true),
--('twoXchromosomes',       180, 'medium', true),
--('AskIndia',              180, 'medium', true),
--('chennai',               600, 'slow', true),
--('hyderabad',             600, 'slow', true),
--('pune',                   600, 'slow', true),
--('kolkata',                600, 'slow', true);
;
