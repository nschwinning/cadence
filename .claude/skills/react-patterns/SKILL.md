---
name: react-patterns
description: React 19 patterns including Server Components, Actions, Suspense, hooks, and component composition
---

# React Patterns

## ⚠️ Cadence Adaptations (READ FIRST)

This skill is written for **Next.js** (Server Components, Server Actions, App Router). The Cadence
frontend is a **Vite + React 19 SPA** with **TanStack Query** for server state, **React Router** for
routing, and **Tailwind** — it has **no server runtime**, so RSC/Server Actions do not exist here.
Use the mapping below; the Cadence column **takes precedence**.

| Skill section | Status in Cadence | Do this instead |
|---|---|---|
| **Server Components** (`async` page components, `fetch` in render) | ❌ N/A (no server) | Fetch with `useQuery` in a client component |
| **Server Actions** (`'use server'`) | ❌ N/A | Mutate with `useMutation` calling the FastAPI endpoint |
| `revalidatePath` (`next/cache`) | ❌ N/A | `queryClient.invalidateQueries({ queryKey })` |
| `redirect` (`next/navigation`) | ❌ N/A | `const navigate = useNavigate(); navigate('/posts')` |
| `error.tsx` route convention | ❌ N/A | React Router `errorElement`, or the Error Boundary class below |
| `useActionState` bound to a Server Action | ⚠️ partial | Prefer `useMutation` (`isPending`, `error`, `data`) for server state |
| **`use()` hook** (Context + promises) | ✅ Applies | — |
| **Suspense boundaries** | ✅ Applies | Pair with React Query `suspense: true` or `useSuspenseQuery` |
| **Error Boundaries** (class component) | ✅ Applies | — |
| **Custom hooks** | ✅ Applies | — |
| **Compound components** | ✅ Applies | — |
| **`useOptimistic`** | ✅ Applies (client) | Or React Query's `onMutate` optimistic-update pattern |
| **Performance rules** | ✅ Applies | — |

### The canonical Cadence data pattern (replaces Server Components + Server Actions)

```tsx
// posts.api.ts — typed client + query keys
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';

export const postKeys = { all: ['posts'] as const };

export function usePosts() {
  return useQuery({
    queryKey: postKeys.all,
    queryFn: (): Promise<Post[]> => api.get('/posts').then(r => r.data),
  });
}

export function useCreatePost() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  return useMutation({
    mutationFn: (input: PostCreate): Promise<Post> =>
      api.post('/posts', input).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: postKeys.all }); // ← replaces revalidatePath
      navigate('/posts');                                // ← replaces redirect()
    },
  });
}
```

```tsx
// NewPostForm.tsx — replaces the Server Action <form action={...}> example
function NewPostForm() {
  const { mutate, isPending, error } = useCreatePost();
  return (
    <form onSubmit={e => {
      e.preventDefault();
      const fd = new FormData(e.currentTarget);
      mutate({ title: String(fd.get('title')), body: String(fd.get('body')) });
    }}>
      <input name="title" required />
      <textarea name="body" required />
      {error && <p role="alert">{(error as Error).message}</p>}
      <button disabled={isPending}>{isPending ? 'Creating…' : 'Create'}</button>
    </form>
  );
}
```

> **Skip** the Server Components, Server Actions, and `useActionState` sections below when working in
> Cadence — they require a Next.js server. Read them only as React 19 background. Everything from
> **Suspense Boundaries** onward applies to our SPA as written.

---

## use() Hook (React 19)

`use()` reads values from Promises and Context directly in render. Unlike other hooks, it can be called inside conditionals and loops.

```tsx
import { use } from 'react';

function UserProfile({ userPromise }: { userPromise: Promise<User> }) {
  const user = use(userPromise);
  return <h1>{user.name}</h1>;
}

function ThemeButton() {
  const theme = use(ThemeContext);
  return <button style={{ background: theme.primary }}>Click</button>;
}
```

Wrap components that use `use()` with a Promise in a `<Suspense>` boundary.

## Server Components

```tsx
// app/users/page.tsx - Server Component (default, no directive needed)
import { UserList } from './UserList';

export default async function UsersPage() {
  const users = await fetch('https://api.example.com/users', {
    next: { revalidate: 60 },
  }).then(r => r.json());

  return <UserList users={users} />;
}

// app/users/UserList.tsx - Still a Server Component
export function UserList({ users }: { users: User[] }) {
  return (
    <ul>
      {users.map(u => (
        <li key={u.id}>
          {u.name}
          <DeleteButton userId={u.id} />
        </li>
      ))}
    </ul>
  );
}
```

Push `'use client'` as deep as possible. Only leaves that need interactivity should be Client Components.

## Server Actions

```tsx
// app/actions.ts
'use server';

import { revalidatePath } from 'next/cache';
import { redirect } from 'next/navigation';

export async function createPost(formData: FormData) {
  const title = formData.get('title') as string;
  const body = formData.get('body') as string;

  await db.insert(posts).values({ title, body });

  revalidatePath('/posts');
  redirect('/posts');
}
```

```tsx
// app/posts/new/page.tsx
import { createPost } from '../actions';

export default function NewPostPage() {
  return (
    <form action={createPost}>
      <input name="title" required />
      <textarea name="body" required />
      <button type="submit">Create</button>
    </form>
  );
}
```

## useActionState (React 19)

```tsx
'use client';

import { useActionState } from 'react';
import { createUser } from './actions';

function SignupForm() {
  const [state, formAction, isPending] = useActionState(createUser, {
    errors: {},
    message: '',
  });

  return (
    <form action={formAction}>
      <input name="email" />
      {state.errors.email && <p>{state.errors.email}</p>}
      <button disabled={isPending}>
        {isPending ? 'Creating...' : 'Sign Up'}
      </button>
      {state.message && <p>{state.message}</p>}
    </form>
  );
}
```

## useOptimistic (React 19)

```tsx
'use client';

import { useOptimistic } from 'react';
import { likePost } from './actions';

function LikeButton({ count, postId }: { count: number; postId: string }) {
  const [optimisticCount, addOptimistic] = useOptimistic(count);

  async function handleLike() {
    addOptimistic(prev => prev + 1);
    await likePost(postId);
  }

  return (
    <form action={handleLike}>
      <button type="submit">{optimisticCount} Likes</button>
    </form>
  );
}
```

## Suspense Boundaries

```tsx
import { Suspense } from 'react';

function Dashboard() {
  return (
    <div>
      <Suspense fallback={<StatsSkeleton />}>
        <StatsPanel />
      </Suspense>
      <div className="grid grid-cols-2">
        <Suspense fallback={<ChartSkeleton />}>
          <RevenueChart />
        </Suspense>
        <Suspense fallback={<ListSkeleton />}>
          <RecentActivity />
        </Suspense>
      </div>
    </div>
  );
}
```

Place Suspense boundaries around independent data-fetching units. Avoid wrapping the entire page in a single boundary (defeats the purpose of streaming).

## Error Boundaries

```tsx
'use client';

import { Component, type ReactNode } from 'react';

class ErrorBoundary extends Component<
  { fallback: ReactNode; children: ReactNode },
  { hasError: boolean }
> {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    reportError(error, info.componentStack);
  }

  render() {
    if (this.state.hasError) return this.props.fallback;
    return this.props.children;
  }
}
```

Or use Next.js `error.tsx` convention for route-level error handling.

## Custom Hooks

```tsx
function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return debounced;
}

function useLocalStorage<T>(key: string, initial: T) {
  const [value, setValue] = useState<T>(() => {
    const stored = localStorage.getItem(key);
    return stored ? JSON.parse(stored) : initial;
  });

  useEffect(() => {
    localStorage.setItem(key, JSON.stringify(value));
  }, [key, value]);

  return [value, setValue] as const;
}
```

Rules for custom hooks:
- Prefix with `use`
- Extract when logic is shared between 2+ components
- Keep hooks focused on a single concern
- Return tuples `[value, setter]` or objects `{ data, error, loading }`

## Compound Components

```tsx
function Tabs({ children }: { children: ReactNode }) {
  const [active, setActive] = useState(0);
  return (
    <TabsContext value={{ active, setActive }}>
      <div role="tablist">{children}</div>
    </TabsContext>
  );
}

Tabs.Tab = function Tab({ index, children }: { index: number; children: ReactNode }) {
  const { active, setActive } = use(TabsContext);
  return (
    <button
      role="tab"
      aria-selected={active === index}
      onClick={() => setActive(index)}
    >
      {children}
    </button>
  );
};

Tabs.Panel = function Panel({ index, children }: { index: number; children: ReactNode }) {
  const { active } = use(TabsContext);
  if (active !== index) return null;
  return <div role="tabpanel">{children}</div>;
};

// Usage
<Tabs>
  <Tabs.Tab index={0}>Profile</Tabs.Tab>
  <Tabs.Tab index={1}>Settings</Tabs.Tab>
  <Tabs.Panel index={0}><ProfileForm /></Tabs.Panel>
  <Tabs.Panel index={1}><SettingsForm /></Tabs.Panel>
</Tabs>
```

## Performance Rules

- Avoid creating objects/arrays in JSX props (causes re-renders)
- Use `React.memo` only after profiling confirms unnecessary re-renders
- Prefer `useMemo`/`useCallback` for expensive computations or stable references passed to memoized children
- Use `key` to reset component state intentionally
- Colocate state: keep state as close to where it is used as possible
- Avoid prop drilling beyond 2 levels; use Context or composition instead
