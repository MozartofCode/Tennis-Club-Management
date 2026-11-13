import { Route, Routes } from 'react-router-dom'
import { Guard } from './components/Guard'
import { Shell } from './components/Shell'
import { Calendar } from './routes/admin/Calendar'
import { CheckIns } from './routes/admin/CheckIns'
import { MemberDetail, Members } from './routes/admin/Members'
import { Matchmaking } from './routes/admin/Matchmaking'
import { Pricing } from './routes/admin/Pricing'
import { Retention } from './routes/admin/Retention'
import { Waitlist } from './routes/admin/Waitlist'
import { Setup } from './routes/admin/Setup'
import { Today } from './routes/admin/Today'
import { CoachSchedule } from './routes/coach/Schedule'
import { Kiosk } from './routes/kiosk/Kiosk'
import { Book } from './routes/member/Book'
import { MemberHome } from './routes/member/Home'
import { Matches } from './routes/member/Matches'
import { MemberOffers } from './routes/member/Offers'
import { Profile } from './routes/member/Profile'
import { MyQr } from './routes/member/Qr'
import { adminNav, coachNav, memberNav } from './routes/nav'
import { Login, MemberSignup, OwnerSignup } from './routes/public/Auth'
import { Landing } from './routes/public/Landing'

export default function App() {
  return (
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
  )
}
