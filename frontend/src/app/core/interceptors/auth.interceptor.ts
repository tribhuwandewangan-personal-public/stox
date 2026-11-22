// Angular HttpInterceptor that adds the required X-Stox-Request header to every outgoing request.

import { Injectable } from '@angular/core';
import { HttpEvent, HttpHandler, HttpInterceptor, HttpRequest } from '@angular/common/http';
import { Observable } from 'rxjs';

@Injectable()
export class AuthInterceptor implements HttpInterceptor {
  intercept(req: HttpRequest<any>, next: HttpHandler): Observable<HttpEvent<any>> {
    const authReq = req.clone({
      setHeaders: {
        // The backend expects exact '1' on this custom header for POST CSRF validation.
        'X-Stox-Request': '1',
        // Ensure JSON payloads are correctly typed.
        'Content-Type': 'application/json'
      }
    });
    return next.handle(authReq);
  }
}
