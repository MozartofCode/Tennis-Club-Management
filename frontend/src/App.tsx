import { Route, Routes } from 'react-router-dom'
import { Guard } from './components/Guard'
import { Shell } from './components/Shell'
import { PageHeader } from './components/ui'
import { Landing } from './routes/public/Landing'
import { Login, MemberSignup, OwnerSignup } from './routes/public/Auth'
import { adminNav, coachNav, memberNav } from './routes/nav'

function Placeholder({ title }: { title: string }) {
  return <PageHeader title={title} sub="Coming in the next phase." />
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route path="/join" element={<MemberSignup />} />
      <Route path="/start" element={<OwnerSignup />} />

      <Route
        path="/admin"
        element={
          <Guard roles={['owner', 'staff']}>
            <Shell nav={adminNav} title="Management" />
          </Guard>
        }
      >
        <Route index element={<Placeholder title="Today" />} />
        <Route path="*" element={<Placeholder title="Management" />} />
      </Route>

      <Route
        path="/app"
        element={
          <Guard roles={['member']}>
            <Shell nav={memberNav} title="Member" />
          </Guard>
        }
      >
        <Route index element={<Placeholder title="Home" />} />
        <Route path="*" element={<Placeholder title="Member" />} />
      </Route>

      <Route
        path="/coach"
        element={
          <Guard roles={['coach']}>
            <Shell nav={coachNav} title="Coach" />
          </Guard>
        }
      >
        <Route index element={<Placeholder title="My schedule" />} />
      </Route>

      <Route path="*" element={<Landing />} />
    </Routes>
  )
}
