import { Controller, Get, Delete, Req } from '@nestjs/common';
import {
  Session,
  type UserSession,
  AllowAnonymous,
  AuthService,
} from '@thallesp/nestjs-better-auth';
import { fromNodeHeaders } from 'better-auth/node';
import type { Request } from 'express';
import type { Auth } from '../auth';

@Controller('users')
export class UsersController {
  constructor(private readonly authService: AuthService<Auth>) {}

  // GET /api/users/me — returns current logged-in user
  @Get('me')
  getMe(@Session() session: UserSession) {
    return {
      user: session.user,
      session: {
        id: session.session.id,
        expiresAt: session.session.expiresAt,
      },
    };
  }

  // GET /api/users/sessions — list all active sessions for current user
  @Get('sessions')
  async getSessions(@Req() req: Request) {
    const sessions = await this.authService.api.listSessions({
      headers: fromNodeHeaders(req.headers),
    });
    return { sessions };
  }

  // DELETE /api/users/sessions — revoke all other sessions
  @Delete('sessions')
  async revokeOtherSessions(@Req() req: Request) {
    await this.authService.api.revokeOtherSessions({
      headers: fromNodeHeaders(req.headers),
    });
    return { success: true };
  }

  // Public health check endpoint
  @Get('health')
  @AllowAnonymous()
  health() {
    return { status: 'ok' };
  }
}
