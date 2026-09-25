-- 在 Supabase Dashboard > SQL Editor 執行一次即可。
create table if not exists public.jobs (
  id          text primary key,
  source      text not null,
  source_id   text not null,
  title       text not null,
  company     text,
  url         text,
  description text,
  location    text,
  country     text,
  city        text,
  remote      boolean,
  category    text,
  seniority   text,
  years_min   int,
  education   text,
  skills      text[] default '{}',
  tags        text[] default '{}',
  salary      text,
  posted_at   date,
  lang        text,
  first_seen  date not null default current_date,
  last_seen   date not null default current_date
);
create index if not exists jobs_last_seen_idx on public.jobs (last_seen);
create index if not exists jobs_skills_idx on public.jobs using gin (skills);

create table if not exists public.daily_stats (
  day    date not null,
  source text not null,
  count  int  not null,
  ok     boolean not null,
  primary key (day, source)
);

-- 只有 GitHub Actions 用 service_role key 寫入；匿名使用者只能讀（網站本身讀的是靜態 JSON，不會打到這裡）。
alter table public.jobs enable row level security;
alter table public.daily_stats enable row level security;
drop policy if exists "public read jobs" on public.jobs;
create policy "public read jobs" on public.jobs for select using (true);
drop policy if exists "public read stats" on public.daily_stats;
create policy "public read stats" on public.daily_stats for select using (true);
