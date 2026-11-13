import { lazy, Suspense } from 'react'
import { Route, Routes } from 'react-router-dom'
import { Guard } from './components/Guard'
import { Shell } from './components/Shell'
import { Spinner } from './components/ui'
import { adminNav, coachNav, memberNav } from './routes/nav'
import { Login, MemberSignup, OwnerSignup } from './routes/public/Auth'
import { Landing } from './routes/public/Landing'

// Route modules load on demand, so members never download the charting or camera libraries.
const named = <T extends string>(load: () => Promise<Record<T, React.ComponentType>>, name: T) =>
  lazy(() => load().then((m) => ({ default: m[name] })))

const Today = named(() => import('./routes/admin/Today'), 'Today')
const Calendar = named(() => import('./routes/admin/Calendar'), 'Calendar')
const Members = named(() => import('./routes/admin/Members'), 'Members')
const MemberDetail = named(() => import('./routes/admin/Members'), 'MemberDetail')
const CheckIns = named(() => import('./routes/admin/CheckIns'), 'CheckIns')
const Pricing = named(() => import('./routes/admin/Pricing'), 'Pricing')
const Waitlist = named(() => import('./routes/admin/Waitlist'), 'Waitlist')
const Retention = named(() => import('./routes/admin/Retention'), 'Retention')
const Matchmaking = named(() => import('./routes/admin/Matchmaking'), 'Matchmaking')
const AnalyticsPage = named(() => import('./routes/admin/Analytics'), 'AnalyticsPage')
const Setup = named(() => import('./routes/admin/Setup'), 'Setup')
const Kiosk = named(() => import('./routes/kiosk/Kiosk'), 'Kiosk')
const MemberHome = named(() => import('./routes/member/Home'), 'MemberHome')
const Book = named(() => import('./routes/member/Book'), 'Book')
const Matches = named(() => import('./routes/member/Matches'), 'Matches')
const MyQr = named(() => import('./routes/member/Qr'), 'MyQr')
const MemberOffers = named(() => import('./routes/member/Offers'), 'MemberOffers')
const Profile = named(() => import('./routes/member/Profile'), 'Profile')
const CoachSchedule = named(() => import('./routes/coach/Schedule'), 'CoachSchedule')

export default function App() {
  return (
    <Suspense fallback={<Spinner />}>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<Login />} />
        <Route path="/join" element={<MemberSignup />} />
        <Route path="/start" element={<OwnerSignup />} />
        <Route
          path="/kiosk"
          element={
            <Guard roles={['owner', 'staff']}>
              <Kiosk />
            </Guard>
          }
        />

        <Route
          path="/admin"
          element={
            <Guard roles={['owner', 'staff']}>
              <Shell nav={adminNav} title="Management" />
            </Guard>
          }
        >
          <Route index element={<Today />} />
          <Route path="calendar" element={<Calendar />} />
          <Route path="members" element={<Members />} />
          <Route path="members/:id" element={<MemberDetail />} />
          <Route path="checkins" element={<CheckIns />} />
          <Route path="pricing" element={<Pricing />} />
          <Route path="waitlist" element={<Waitlist />} />
          <Route path="retention" element={<Retention />} />
          <Route path="matchmaking" element={<Matchmaking />} />
          <Route path="analytics" element={<AnalyticsPage />} />
          <Route path="setup" element={<Setup />} />
        </Route>

        <Route
          path="/app"
          element={
            <Guard roles={['member']}>
              <Shell nav={memberNav} title="Member" />
            </Guard>
          }
        >
          <Route index element={<MemberHome />} />
          <Route path="book" element={<Book />} />
          <Route path="matches" element={<Matches />} />
          <Route path="qr" element={<MyQr />} />
          <Route path="offers" element={<MemberOffers />} />
          <Route path="profile" element={<Profile />} />
        </Route>

        <Route
          path="/coach"
          element={
            <Guard roles={['coach']}>
              <Shell nav={coachNav} title="Coach" />
            </Guard>
          }
        >
          <Route index element={<CoachSchedule />} />
        </Route>

        <Route path="*" element={<Landing />} />
      </Routes>
    </Suspense>
  )
}
