import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import ProtectedRoute from './components/ProtectedRoute'
import Home from './pages/Home'
import Chat from './pages/Chat'
import Admin from './pages/Admin'
import Settings from './pages/Settings'
import Profile from './pages/Profile'
import Webhooks from './pages/Webhooks'
import Documents from './pages/Documents'
import NotFound from './pages/NotFound'
import Login from './pages/Login'
import ForgotPassword from './pages/ForgotPassword'
import ResetPassword from './pages/ResetPassword'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route element={<ProtectedRoute><Layout /></ProtectedRoute>}>
        <Route path="/" element={<Home />} />
        <Route path="/chat/:id" element={<Chat />} />
        <Route path="/admin" element={<Admin />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/profile" element={<Profile />} />
        <Route path="/documents" element={<Documents />} />
        <Route path="/webhooks" element={<Webhooks />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}
